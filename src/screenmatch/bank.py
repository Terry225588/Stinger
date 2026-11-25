"""从 Excel 或 JSON 读入题库。空选项、对不上的答案会整行跳过。"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from screenmatch.normalize import (
    cell_to_str,
    clean_analysis,
    normalize_match_text,
    stem_fingerprint,
    strip_option_prefix,
    to_halfwidth,
)

TYPE_ORDER = (
    "单项选择题",
    "多项选择题",
    "单选题",
    "多选题",
    "判断题",
    "单选",
    "多选",
    "判断",
    "single",
    "multi",
    "judgment",
)
TYPE_MAP = {
    "单项选择题": "single",
    "多项选择题": "multi",
    "单选题": "single",
    "多选题": "multi",
    "判断题": "judgment",
    "单选": "single",
    "多选": "multi",
    "判断": "judgment",
    "single": "single",
    "multi": "multi",
    "judgment": "judgment",
}
TYPE_LABEL = {"single": "单选题", "multi": "多选题", "judgment": "判断题"}
HEADER_ALIASES = {
    "题目": "题目",
    "题干": "题目",
    "试题内容": "题目",
    "题型": "题型",
    "类型": "题型",
    "答案": "答案",
    "正确答案": "答案",
    "难度": "难度",
    "试题依据": "试题依据",
    "依据": "试题依据",
    "试题解析": "试题解析",
    "解析": "试题解析",
    "保命题": "保命题",
    **{letter: letter for letter in "ABCDEF"},
}
ENGLISH_FIELDS = {
    "type": "题型",
    "qtype": "题型",
    "stem": "题目",
    "answer": "答案",
    "difficulty": "难度",
    "basis": "试题依据",
    "analysis": "试题解析",
    "tag": "保命题",
}


class BankFormatError(ValueError):
    """整个文件无法作为题库读取。"""


@dataclass(frozen=True)
class Question:
    qtype: str
    type_label: str
    stem: str
    options: dict[str, str]
    answer: str
    difficulty: str
    basis: str
    analysis: str
    tag: str
    source_row: int
    fingerprint: str
    bank_name: str = ""

    def to_dict(self) -> dict:
        return {
            "qtype": self.qtype,
            "type_label": self.type_label,
            "stem": self.stem,
            "options": dict(self.options),
            "answer": self.answer,
            "difficulty": self.difficulty,
            "basis": self.basis,
            "analysis": self.analysis,
            "tag": self.tag,
            "source_row": self.source_row,
            "fingerprint": self.fingerprint,
            "bank_name": self.bank_name,
        }


@dataclass
class RejectedRow:
    row: int
    reason: str


@dataclass
class ImportReport:
    source_name: str
    questions: list[Question]
    rejected: list[RejectedRow] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.questions)

    def counts(self) -> dict[str, int]:
        totals = {"single": 0, "multi": 0, "judgment": 0}
        for question in self.questions:
            totals[question.qtype] = totals.get(question.qtype, 0) + 1
        return totals


class QuestionBank:
    def __init__(self, questions: list[Question], source_name: str = ""):
        self.questions = list(questions)
        self.source_name = source_name
        self.by_fingerprint: dict[str, list[Question]] = {}
        for question in self.questions:
            self.by_fingerprint.setdefault(question.fingerprint, []).append(question)

    def counts(self) -> dict[str, int]:
        totals = {"single": 0, "multi": 0, "judgment": 0}
        for question in self.questions:
            totals[question.qtype] = totals.get(question.qtype, 0) + 1
        return totals

    @property
    def duplicate_groups(self) -> list[list[Question]]:
        return [group for group in self.by_fingerprint.values() if len(group) > 1]


def load_bank(path: str | Path) -> tuple[QuestionBank, ImportReport]:
    file_path = Path(path)
    if not file_path.is_file():
        raise BankFormatError(f"找不到文件：{file_path}")
    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        report = _load_xlsx(file_path)
    elif suffix == ".json":
        report = _load_json(file_path)
    else:
        raise BankFormatError("只支持 .xlsx 和 .json。请直接选择 Excel，不必先转换。")
    return QuestionBank(report.questions, report.source_name), report


def save_bank_cache(path: str | Path, bank: QuestionBank) -> None:
    payload = {
        "version": 1,
        "source_name": bank.source_name,
        "questions": [question.to_dict() for question in bank.questions],
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_bank_cache(path: str | Path) -> QuestionBank:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    questions: list[Question] = []
    for item in payload.get("questions", []):
        try:
            questions.append(_question_from_cache(item))
        except (KeyError, TypeError, ValueError):
            continue
    return QuestionBank(questions, str(payload.get("source_name") or file_path.name))


def canonical_type(raw: object) -> str | None:
    text = to_halfwidth(cell_to_str(raw)).strip()
    text = text.replace("【", "").replace("】", "").strip()
    if text in TYPE_MAP:
        return TYPE_MAP[text]
    for key in TYPE_ORDER:
        if key in text:
            return TYPE_MAP[key]
    return None


def _question_from_cache(item: dict) -> Question:
    options = {str(key): str(value) for key, value in dict(item["options"]).items() if str(value).strip()}
    qtype = str(item["qtype"])
    if qtype not in TYPE_LABEL:
        raise ValueError(qtype)
    stem = str(item["stem"])
    return Question(
        qtype=qtype,
        type_label=str(item.get("type_label") or TYPE_LABEL[qtype]),
        stem=stem,
        options=options,
        answer=str(item["answer"]),
        difficulty=str(item.get("difficulty") or ""),
        basis=str(item.get("basis") or ""),
        analysis=clean_analysis(item.get("analysis")),
        tag=str(item.get("tag") or ""),
        source_row=int(item.get("source_row") or 0),
        fingerprint=stem_fingerprint(stem),
        bank_name=str(item.get("bank_name") or ""),
    )


def _load_xlsx(file_path: Path) -> ImportReport:
    try:
        import openpyxl
    except ImportError as exc:
        raise BankFormatError("没有安装 openpyxl，无法读取 Excel。") from exc
    # 不用 read_only：表头和数据要各扫一遍。文本单元格保持原样，不把 "100.0" 转成数字。
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Workbook contains no default style",
            category=UserWarning,
        )
        workbook = openpyxl.load_workbook(file_path, data_only=False, read_only=False)
    try:
        sheet, header_row, columns = _choose_sheet(workbook)
        questions, rejected = _consume_rows(sheet, header_row, columns)
    finally:
        workbook.close()
    return ImportReport(file_path.name, questions, rejected)


def _choose_sheet(workbook):
    best = None
    for name in workbook.sheetnames:
        sheet = workbook[name]
        found = _find_header(sheet)
        if found is None:
            continue
        header_row, columns = found
        score = sheet.max_row or 0
        if best is None or score > best[0]:
            best = (score, sheet, header_row, columns)
    if best is None:
        raise BankFormatError("前 10 行里没有找到表头。至少需要：题型、题目、答案，以及选项 A–F。")
    return best[1], best[2], best[3]


def _find_header(sheet) -> tuple[int, dict[str, int]] | None:
    for index, row in enumerate(sheet.iter_rows(min_row=1, max_row=10, values_only=True), start=1):
        mapping: dict[str, int] = {}
        for col_index, value in enumerate(row):
            name = HEADER_ALIASES.get(cell_to_str(value).strip())
            if name and name not in mapping:
                mapping[name] = col_index
        if {"题型", "题目", "答案"} <= set(mapping):
            return index, mapping
    return None


def _consume_rows(sheet, header_row: int, columns: dict[str, int]):
    questions: list[Question] = []
    rejected: list[RejectedRow] = []
    for row_number, row in enumerate(
        sheet.iter_rows(min_row=header_row + 1, values_only=True),
        start=header_row + 1,
    ):
        record = {
            name: row[col] if col < len(row) else None
            for name, col in columns.items()
        }
        if not any(cell_to_str(value).strip() for value in record.values()):
            continue
        question, reason = _question_from_record(record, row_number)
        if question is None:
            rejected.append(RejectedRow(row_number, reason or "无法导入"))
        else:
            questions.append(question)
    return questions, rejected


def _load_json(file_path: Path) -> ImportReport:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BankFormatError(f"JSON 无法解析：{exc}") from exc
    if isinstance(payload, dict):
        rows = payload.get("questions", payload.get("data"))
    else:
        rows = payload
    if not isinstance(rows, list):
        raise BankFormatError("JSON 需要是题目数组，或包含 questions 数组的对象。")
    questions: list[Question] = []
    rejected: list[RejectedRow] = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            rejected.append(RejectedRow(index, "这一项不是对象"))
            continue
        record = _json_record(item)
        row_number = int(item.get("source_row") or index)
        question, reason = _question_from_record(record, row_number)
        if question is None:
            rejected.append(RejectedRow(row_number, reason or "无法导入"))
        else:
            questions.append(question)
    return ImportReport(file_path.name, questions, rejected)


def _json_record(item: dict) -> dict:
    record: dict[str, object] = {}
    for key, value in item.items():
        name = str(key).strip()
        if name in HEADER_ALIASES:
            record[HEADER_ALIASES[name]] = value
        elif name in ENGLISH_FIELDS:
            record[ENGLISH_FIELDS[name]] = value
    options = item.get("options")
    if isinstance(options, dict):
        for key, value in options.items():
            letter = to_halfwidth(str(key)).strip().upper()
            if letter in "ABCDEF":
                record[letter] = value
    return record


def _question_from_record(record: dict, row_number: int) -> tuple[Question | None, str | None]:
    qtype = canonical_type(record.get("题型"))
    if qtype is None:
        return None, "题型无法识别"
    stem = cell_to_str(record.get("题目")).strip()
    if not stem_fingerprint(stem):
        return None, "题目为空"
    options, option_error = _collect_options(record)
    if option_error:
        return None, option_error
    count = len(options)
    if qtype == "judgment":
        if count != 2:
            return None, "判断题需要 2 个选项"
    elif count < 3 or count > 6:
        return None, "单选题和多选题需要 3 到 6 个选项，且中间不能空着"
    try:
        answer = _normalize_answer(record.get("答案"), options, qtype)
    except ValueError as exc:
        return None, str(exc)
    question = Question(
        qtype=qtype,
        type_label=TYPE_LABEL[qtype],
        stem=stem,
        options=options,
        answer=answer,
        difficulty=cell_to_str(record.get("难度")).strip(),
        basis=cell_to_str(record.get("试题依据")).strip(),
        analysis=clean_analysis(record.get("试题解析")),
        tag=cell_to_str(record.get("保命题")).strip(),
        source_row=row_number,
        fingerprint=stem_fingerprint(stem),
    )
    return question, None


def _collect_options(record: dict) -> tuple[dict[str, str], str | None]:
    pairs: list[tuple[str, str]] = []
    for letter in "ABCDEF":
        text = strip_option_prefix(cell_to_str(record.get(letter)).strip())
        pairs.append((letter, text))
    while pairs and not pairs[-1][1]:
        pairs.pop()
    if any(not text for _, text in pairs):
        return {}, "存在空选项"
    return {letter: text for letter, text in pairs if text}, None


def _normalize_answer(raw: object, options: dict[str, str], qtype: str) -> str:
    text = to_halfwidth(cell_to_str(raw)).strip()
    if not text:
        raise ValueError("答案为空")
    found = {ch for ch in text.upper() if ch in "ABCDEF"}
    letters = "".join(ch for ch in "ABCDEF" if ch in found)
    if not letters and qtype == "judgment":
        word = normalize_match_text(text)
        if word in {"正确", "对", "是", "true", "t"}:
            letters = _letter_for(options, {"正确", "对"}) or ""
        elif word in {"错误", "错", "否", "false", "f"}:
            letters = _letter_for(options, {"错误", "错"}) or ""
    if not letters:
        raise ValueError("答案无法对应到选项")
    if any(ch not in options for ch in letters):
        raise ValueError("答案里的字母超出了已有选项")
    if qtype == "single" and len(letters) != 1:
        raise ValueError("单选题答案只能有一个字母")
    if qtype == "judgment" and len(letters) != 1:
        raise ValueError("判断题答案只能有一个字母")
    if qtype == "multi" and len(letters) < 2:
        raise ValueError("多选题答案至少需要两个字母")
    return letters


def _letter_for(options: dict[str, str], words: set[str]) -> str | None:
    hits = [letter for letter, text in options.items() if normalize_match_text(text) in words]
    if len(hits) == 1:
        return hits[0]
    return None


ALL_BANKS = "全部题库"


def bank_display_name(path: str | Path) -> str:
    return Path(path).stem.strip() or "未命名题库"


class BankCatalog:
    """多个题库按文件名分开保存。全部模式下不合并同题干冲突。"""

    def __init__(self) -> None:
        self.entries: dict[str, QuestionBank] = {}
        self.mode = ALL_BANKS

    def add_files(self, paths) -> list[tuple[str, ImportReport | None, str]]:
        """按文件名逐个导入。失败的文件记原因，不编造题目。"""
        results: list[tuple[str, ImportReport | None, str]] = []
        for path in paths:
            file = Path(path)
            try:
                _stored, report = self.add_file(file)
            except (BankFormatError, OSError, ValueError, Exception) as exc:
                results.append((file.name, None, str(exc)))
                continue
            results.append((file.name, report, ""))
        return results

    def add_file(self, path: str | Path) -> tuple[QuestionBank, ImportReport]:
        from dataclasses import replace

        loaded, report = load_bank(path)
        name = bank_display_name(path)
        tagged = [replace(question, bank_name=name) for question in loaded.questions]
        stored = QuestionBank(tagged, name)
        self.entries[name] = stored
        return stored, report

    def names(self) -> list[str]:
        return sorted(self.entries)

    def use(self, mode: str) -> None:
        if mode == ALL_BANKS or mode in self.entries:
            self.mode = mode

    def active(self) -> QuestionBank:
        if self.mode != ALL_BANKS and self.mode in self.entries:
            return self.entries[self.mode]
        questions: list[Question] = []
        for bank in self.entries.values():
            questions.extend(bank.questions)
        return QuestionBank(questions, ALL_BANKS)

    def save(self, directory: str | Path) -> None:
        root = Path(directory)
        folder = root / "banks"
        folder.mkdir(parents=True, exist_ok=True)
        kept: list[str] = []
        for name, bank in self.entries.items():
            slug = _bank_slug(name)
            save_bank_cache(folder / f"{slug}.json", bank)
            kept.append(slug)
        for old in folder.glob("*.json"):
            if old.stem not in kept:
                old.unlink()
        payload = {"mode": self.mode, "order": self.names()}
        (root / "catalog.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, directory: str | Path) -> "BankCatalog":
        catalog = cls()
        root = Path(directory)
        folder = root / "banks"
        if folder.is_dir():
            for file in sorted(folder.glob("*.json")):
                bank = load_bank_cache(file)
                name = bank.source_name or file.stem
                catalog.entries[name] = bank
        meta = root / "catalog.json"
        if meta.is_file():
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
                catalog.use(str(payload.get("mode") or ALL_BANKS))
            except (OSError, ValueError):
                catalog.mode = ALL_BANKS
        return catalog


def format_batch_report(results: list[tuple[str, ImportReport | None, str]]) -> str:
    lines = [f"导入 {len(results)} 个文件。"]
    if not results:
        lines.append("没有选到 Excel 文件。")
    for name, report, error in results:
        if report is None:
            lines.append(f"{name}：失败。{error}")
            continue
        lines.append(f"{name}：成功 {report.valid_count} 题，跳过 {len(report.rejected)} 行。")
        for item in report.rejected[:8]:
            lines.append(f"  第 {item.row} 行：{item.reason}")
    return "\n".join(lines) + "\n"


def _bank_slug(name: str) -> str:
    import re

    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name).strip("._")
    return cleaned[:80] or "bank"
