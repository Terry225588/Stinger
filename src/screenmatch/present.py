"""把匹配结果写成界面上的中文说明。解析只使用题库原文。"""

from __future__ import annotations

from screenmatch.match import MatchOutcome

_BANNERS = {
    "high": "高相似",
    "partial": "片段候选，不是逐字核对通过",
    "medium": "仅供参考：题干不完全确定",
    "low": "没有确定答案：只有一些弱相似的题",
    "ambiguous": "不能确定：题干对应多道题，或几道题太接近",
    "none": "没有匹配",
}
_NO_ANALYSIS = "题库未提供解析"


def shows_current_answer(outcome: MatchOutcome) -> bool:
    """低置信或答案互相冲突时，不把任何一条当成确定答案。"""
    if outcome.needs_review:
        return False
    if outcome.status != "high" or outcome.chosen is None or not outcome.verified:
        return False
    return True


def candidate_window(outcome: MatchOutcome, expanded: bool) -> list:
    limit = 5 if expanded else 3
    return list(outcome.candidates[:limit])


def format_outcome(outcome: MatchOutcome, ocr_text: str = "") -> str:
    lines: list[str] = [_BANNERS.get(outcome.status, "没有匹配"), ""]
    lines.append(f"题干相似度 {outcome.score:.2f}（不是正确率，也不是把握）")
    if outcome.needs_review or outcome.status in {"partial", "ambiguous", "medium", "low", "none"}:
        lines.append("待确认：这不是确定答案。")
    if outcome.verified:
        if outcome.chosen is not None and outcome.chosen.qtype == "judgment":
            lines.append("题干与题库逐字一致。判断题只显示对或错，不显示 A、B。")
        else:
            lines.append("题干与题库逐字一致。字母是否就是网页上的字母，要看下面有没有写明已经对应。")
    elif shows_current_answer(outcome):
        lines.append("这条按相似度列出，不是逐字确定。")
    else:
        lines.append("当前没有可直接采用的答案。")
    for reason in outcome.reasons:
        lines.append(reason)
    lines.append("")
    if shows_current_answer(outcome):
        lines.extend(_question_block(outcome))
    shown = candidate_window(outcome, expanded=True)
    if shown:
        lines.append("候选题目（相似度够高才列出，不够的不凑数）")
        for index, candidate in enumerate(shown, start=1):
            lines.extend(_candidate_lines(candidate, index))
        lines.append("")
    lines.append("识别到的题干")
    lines.append(outcome.screen_stem or "（没有分离出题干）")
    lines.append("")
    lines.append("识别原文")
    lines.append(ocr_text.strip() or "（空）")
    return "\n".join(lines).rstrip() + "\n"


def format_import(valid: int, counts: dict[str, int], rejected: list[tuple[int, str]], replaced: bool) -> str:
    lines = [
        f"已导入 {valid} 题：单选 {counts.get('single', 0)}，多选 {counts.get('multi', 0)}，判断 {counts.get('judgment', 0)}。",
        f"跳过 {len(rejected)} 行。",
    ]
    if replaced:
        lines.append("这份题库已按文件名保存。其他题库还在。")
    if rejected:
        lines.append("跳过原因（最多 12 行）：")
        for row, reason in rejected[:12]:
            lines.append(f"第 {row} 行：{reason}")
    return "\n".join(lines) + "\n"


def _question_block(outcome: MatchOutcome) -> list[str]:
    question = outcome.chosen
    assert question is not None
    face = judgment_face(question)
    if face:
        lines = [
            _meta(question),
            "",
            question.stem,
            "",
            "答案",
            face,
            "",
            "解析",
            question.analysis or _NO_ANALYSIS,
        ]
        extra = []
        if question.difficulty:
            extra.append(f"难度：{question.difficulty}")
        if question.basis:
            extra.append(f"试题依据：{question.basis}")
        if question.tag:
            extra.append(f"保命题：{question.tag}")
        if extra:
            lines.append("")
            lines.append("  ".join(extra))
        lines.append("")
        return lines
    lines = [
        _meta(question),
        "",
        question.stem,
        "",
        "答案原文",
    ]
    if outcome.remapped:
        # 只在全部答案字母都完成对应时展示画面字母。
        # remapped 是排序后的画面字母，和题库字母逐项对应关系在 letter 映射里不保留顺序差异时仍可按排序对照。
        lines.append("题库字母与画面字母都列在下面。请同时看选项原文。")
    for letter, text in outcome.answer_texts:
        screen_letter = outcome.screen_for_answer.get(letter)
        if screen_letter:
            lines.append(f"{letter}. {text}    （画面上的 {screen_letter}）")
        else:
            lines.append(f"{letter}. {text}")
    lines.append("")
    lines.append(f"题库记录的字母：{question.answer}")
    if outcome.remapped:
        lines.append(f"按当前画面选项对应的字母：{outcome.remapped}")
    else:
        lines.append("未能对应到画面字母。")
    if outcome.letter_note:
        lines.append(outcome.letter_note)
    lines.append("")
    lines.append("题库选项")
    answer_set = set(question.answer)
    for letter, text in question.options.items():
        mark = "    ← 题库答案" if letter in answer_set else ""
        lines.append(f"{letter}. {text}{mark}")
    lines.append("")
    lines.append("画面上识别到的选项")
    if outcome.screen_options:
        for letter, text in outcome.screen_options.items():
            lines.append(f"{letter}. {text}")
    else:
        lines.append("（没有识别到选项）")
    lines.append("")
    lines.append("解析")
    lines.append(question.analysis or _NO_ANALYSIS)
    extra = []
    if question.difficulty:
        extra.append(f"难度：{question.difficulty}")
    if question.basis:
        extra.append(f"试题依据：{question.basis}")
    if question.tag:
        extra.append(f"保命题：{question.tag}")
    if extra:
        lines.append("")
        lines.append("  ".join(extra))
    lines.append("")
    return lines


SIMILARITY_HINT = "题干匹配度是题干相似度乘以 100，不是把握，也不是正确率。"
STEM_EXCERPT = 12


def stem_excerpt(stem: str, limit: int = STEM_EXCERPT) -> str:
    compact = "".join(stem.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "…"


REVIEW_BADGE = "待确认"


def needs_review_badge(outcome: MatchOutcome) -> bool:
    """低置信、片段、歧义或关键差异时标「待确认」，不把结果升成确定答案。"""
    if outcome.needs_review or not outcome.verified:
        return True
    return outcome.status in {"partial", "ambiguous", "medium", "low", "none"}


def short_panel_status(notice: str) -> str:
    if not notice:
        return ""
    if "暂停" in notice:
        return "已暂停"
    if "没有识别" in notice or "无识别" in notice:
        return "无识别"
    if "失败" in notice or "出错" in notice:
        return "出错"
    return "已作废"


def judgment_face(question) -> str | None:
    """判断题只按选项含义显示对或错，不显示 A/B。"""
    if question.qtype != "judgment":
        return None
    from screenmatch.normalize import normalize_match_text

    text = normalize_match_text(question.options.get(question.answer, ""))
    if text in {"正确", "对"}:
        return "对"
    if text in {"错误", "错"}:
        return "错"
    stored = question.options.get(question.answer, "").strip()
    return stored or None


def compact_panel_rows(outcome: MatchOutcome, expanded: bool) -> list[dict]:
    review = needs_review_badge(outcome)
    rows: list[dict] = []
    for candidate in candidate_window(outcome, expanded):
        face = judgment_face(candidate.question)
        if face:
            letter_line = face
            texts: list[str] = []
        else:
            letters = candidate.bank_letters or candidate.question.answer
            if candidate.screen_letters:
                letter_line = f"画面 {candidate.screen_letters}"
            else:
                letter_line = f"题库 {letters}"
            texts = [
                text
                for _letter, text in (
                    candidate.answer_texts
                    or tuple(
                        (letter, candidate.question.options.get(letter, ""))
                        for letter in candidate.question.answer
                    )
                )
                if text
            ]
        rows.append(
            {
                "percent": int(round(candidate.score * 100)),
                "excerpt": stem_excerpt(candidate.question.stem),
                "letter_line": letter_line,
                "contents": texts,
                "review": review,
                "bank": candidate.question.bank_name,
            }
        )
    return rows


def format_panel(outcome: MatchOutcome | None, *, expanded: bool, notice: str, show_current: bool) -> str:
    """浮动面板只保留匹配度和红色答案。show_current 不再单独再画一遍最佳项。"""
    del show_current
    if outcome is None:
        status = short_panel_status(notice)
        return (status + "\n") if status else "\n"
    lines: list[str] = []
    for row in compact_panel_rows(outcome, expanded):
        badge = f"  {REVIEW_BADGE}" if row["review"] else ""
        bank = f"  {row['bank']}" if row.get("bank") else ""
        lines.append(f"题干匹配度 {row['percent']}%  {row['excerpt']}{bank}{badge}")
        lines.append(row["letter_line"])
        lines.extend(row["contents"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _candidate_lines(candidate, index: int) -> list[str]:
    mark = "低匹配，不要当成同一题。 " if candidate.low_match else ""
    lines = [
        f"{index}. {candidate.question.type_label}  相似度 {candidate.score:.2f}（不是正确率）  {mark}".rstrip()
    ]
    lines.append("   " + _short_stem(candidate.question.stem))
    face = judgment_face(candidate.question)
    if face:
        lines.append(f"   答案：{face}")
    else:
        texts = candidate.answer_texts or tuple(
            (letter, candidate.question.options.get(letter, "")) for letter in candidate.question.answer
        )
        lines.append("   答案原文：" + "；".join(f"{letter}. {text}" for letter, text in texts))
        letters = candidate.bank_letters or candidate.question.answer
        lines.append(f"   题库字母：{letters}")
    lines.append("   保命题：" + (candidate.question.tag or "（空）"))
    lines.append("   解析：" + (candidate.question.analysis or "题库未提供解析"))
    if candidate.screen_letters and face is None:
        lines.append(f"   画面字母：{candidate.screen_letters}（选项文字已对应）")
    return lines


def _short_stem(stem: str, limit: int = 32) -> str:
    compact = " ".join(stem.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "…"


def _meta(question) -> str:
    bits = [question.type_label, f"题库第 {question.source_row} 行"]
    return "    ".join(bits)


def _answer_line(question) -> str:
    face = judgment_face(question)
    if face:
        return face
    parts = [f"{letter}. {question.options.get(letter, '')}" for letter in question.answer]
    return "；".join(parts)


def _option_line(question) -> str:
    return " | ".join(f"{letter}. {text}" for letter, text in question.options.items())
