from openpyxl import Workbook

from screenmatch.bank import BankFormatError, load_bank


HEADERS = ["题型", "题目", "A", "B", "C", "D", "E", "F", "答案", "难度", "试题依据", "试题解析", "保命题"]


def _book(rows: list[list], path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for row in rows:
        padded = list(row) + [""] * (len(HEADERS) - len(row))
        sheet.append(padded[: len(HEADERS)])
    workbook.save(path)


def test_import_counts_validation_and_types(tmp_path):
    path = tmp_path / "bank.xlsx"
    _book(
        [
            ["单选题", "传输层负责什么", "端到端", "路由", "调制", "编码", "", "", "A", "易", "教材", "", "否"],
            ["多选题", "下面哪些属于传输层", "可靠传输", "差错控制", "流量控制", "域名解析", "调制解调", "", "A,C,E", "", "", "无", ""],
            ["判断题", "操作系统是系统软件", "正确", "错误", "", "", "", "", "A", "", "", "", ""],
            ["判断", "防火墙只能是硬件", "正确", "错误", "", "", "", "", "错误", "", "", "暂无", "是"],
            ["单选", "存在空选项的题", "甲", "乙", "", "丁", "", "", "A", "", "", "", ""],
            ["单选题", "缺少答案的题", "甲", "乙", "丙", "", "", "", "", "", "", "", ""],
            ["填空", "这不是支持的题型", "甲", "乙", "丙", "", "", "", "A", "", "", "", ""],
            ["单选题", "只有两个选项", "甲", "乙", "", "", "", "", "A", "", "", "", ""],
            ["多选题", "多选却只有一个答案", "甲", "乙", "丙", "丁", "", "", "B", "", "", "", ""],
            ["多选题", "六个选项都入选", "一", "二", "三", "四", "五", "六", "ABDF", "", "", "", ""],
            ["单选题", "数值选项题", "100.0", "200", "三百", "", "", "", "A", "", "", "", ""],
        ],
        path,
    )
    bank, report = load_bank(path)
    counts = report.counts()
    assert report.valid_count == 6
    assert counts == {"single": 2, "multi": 2, "judgment": 2}
    assert bank.counts() == counts
    reasons = {item.reason for item in report.rejected}
    assert "存在空选项" in reasons
    assert "答案为空" in reasons
    assert "题型无法识别" in reasons
    assert "单选题和多选题需要 3 到 6 个选项，且中间不能空着" in reasons
    assert "多选题答案至少需要两个字母" in reasons
    judgment = next(q for q in bank.questions if q.stem.startswith("防火墙"))
    assert judgment.qtype == "judgment"
    assert judgment.answer == "B"
    assert judgment.analysis == ""
    assert judgment.tag == "是"
    numeric = next(q for q in bank.questions if q.stem == "数值选项题")
    assert numeric.options["A"] == "100.0"
    multi = next(q for q in bank.questions if "六个选项" in q.stem)
    assert list(multi.options) == list("ABCDEF")
    assert multi.answer == "ABDF"
    explained = next(q for q in bank.questions if q.stem == "传输层负责什么")
    assert explained.analysis == ""
    assert explained.basis == "教材"
    assert explained.difficulty == "易"


def test_replace_bank_discards_previous_questions(tmp_path):
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    _book(
        [["单选题", "第一份题库里的唯一题目内容", "甲", "乙", "丙", "", "", "", "A", "", "", "", ""]],
        first,
    )
    _book(
        [["判断题", "第二份题库的判断题内容完全不同", "正确", "错误", "", "", "", "", "A", "", "", "", ""]],
        second,
    )
    bank, _report = load_bank(first)
    assert bank.counts()["single"] == 1
    replaced, report = load_bank(second)
    assert report.valid_count == 1
    assert replaced.counts()["judgment"] == 1
    assert all("第一份" not in q.stem for q in replaced.questions)


def test_json_import_uses_same_rules(tmp_path):
    path = tmp_path / "bank.json"
    path.write_text(
        """
        {"questions": [
          {"type": "单选题", "stem": "JSON 导入的单选题干足够长", "options": {"A": "甲", "B": "乙", "C": "丙"}, "answer": "B", "source_row": 9},
          {"题型": "多选题", "题目": "JSON 中文表头的多选题干", "A": "一", "B": "二", "C": "三", "D": "四", "答案": "BD"}
        ]}
        """,
        encoding="utf-8",
    )
    bank, report = load_bank(path)
    assert report.valid_count == 2
    assert bank.counts() == {"single": 1, "multi": 1, "judgment": 0}
    assert next(q for q in bank.questions if q.source_row == 9).answer == "B"


def test_bad_file_is_a_format_error(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("不是题库", encoding="utf-8")
    try:
        load_bank(path)
    except BankFormatError as exc:
        assert "xlsx" in str(exc)
    else:
        raise AssertionError("应该拒绝未知格式")
