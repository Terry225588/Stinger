from screenmatch.match import match_text
from screenmatch.present import format_outcome
from tests.helpers import bank, question

LONG = "在分组交换网络里传输层提供端到端可靠传输和差错控制"
PARTIAL_MEDIUM = LONG[:16]
PARTIAL_HIGH_STEM = "在分组交换网络里传输层提供端到端可靠传输以及差错控制与流量控制能力"
PARTIAL_HIGH = PARTIAL_HIGH_STEM[:24]


def _single():
    return question(
        stem="传输层的主要职责是提供端到端的可靠传输",
        options={"A": "端到端可靠传输", "B": "路由选择", "C": "调制解调", "D": "域名解析"},
        answer="A",
        source_row=12,
        basis="教材第 4 章",
        tag="否",
    )


def test_single_choice_remaps_shuffled_options_and_shows_text():
    stored = _single()
    outcome = match_text(
        bank(stored),
        "12. 传输层的主要职责是提供端到端的可靠传输（）\n"
        "A. 路由选择\nB. 调制解调\nC. 端到端可靠传输\nD. 域名解析\n",
    )
    assert outcome.status == "high"
    assert outcome.confident is True
    assert outcome.chosen is stored
    assert outcome.answer_texts == [("A", "端到端可靠传输")]
    assert outcome.remapped == "C"
    text = format_outcome(outcome, "ocr")
    assert "端到端可靠传输" in text
    assert "题库记录的字母：A" in text
    assert "按当前画面选项对应的字母：C" in text
    assert "题库未提供解析" in text
    assert "教材第 4 章" in text
    assert "因此可以得出" not in text


def test_multi_and_six_options_remap_together():
    stored = question(
        qtype="multi",
        stem="下列哪些属于传输层能够提供的能力",
        options={
            "A": "可靠传输",
            "B": "差错控制",
            "C": "流量控制",
            "D": "域名解析",
            "E": "调制解调",
            "F": "拥塞控制",
        },
        answer="ABF",
        source_row=20,
    )
    outcome = match_text(
        bank(stored),
        "下列哪些属于传输层能够提供的能力\n"
        "A. 域名解析\nB. 可靠传输\nC. 差错控制\nD. 调制解调\nE. 拥塞控制\nF. 流量控制\n",
    )
    assert outcome.status == "high"
    assert outcome.chosen.answer == "ABF"
    assert [text for _, text in outcome.answer_texts] == ["可靠传输", "差错控制", "拥塞控制"]
    assert outcome.remapped == "BCE"
    text = format_outcome(outcome)
    assert "可靠传输    （画面上的 B）" in text
    assert "差错控制    （画面上的 C）" in text
    assert "拥塞控制    （画面上的 E）" in text


def test_judgment_swapped_correct_and_wrong():
    stored = question(
        qtype="judgment",
        stem="操作系统属于系统软件这一说法是否成立",
        options={"A": "正确", "B": "错误"},
        answer="A",
        source_row=30,
    )
    outcome = match_text(
        bank(stored),
        "操作系统属于系统软件这一说法是否成立\nA. 错误\nB. 正确\n",
    )
    assert outcome.status == "high"
    assert outcome.answer_texts == [("A", "正确")]
    assert outcome.remapped == "B"
    plain = match_text(bank(stored), "操作系统属于系统软件这一说法是否成立\n错误\n正确\n")
    assert plain.remapped == "B"


def test_duplicate_stem_without_options_is_not_confident():
    stem = "重复题干用于区分单选和多选时不能只看题目本身"
    single = question(
        stem=stem,
        options={"A": "苹果", "B": "香蕉", "C": "梨"},
        answer="A",
        source_row=77,
    )
    multi = question(
        qtype="multi",
        stem=stem,
        options={"A": "红", "B": "绿", "C": "蓝", "D": "黄"},
        answer="ABC",
        source_row=545,
    )
    outcome = match_text(bank(single, multi), stem + "（）")
    assert outcome.status == "ambiguous"
    assert outcome.confident is False
    assert outcome.chosen is None
    assert outcome.answer_texts == []
    rows = {item.question.source_row for item in outcome.candidates}
    assert rows == {77, 545}
    text = format_outcome(outcome, stem)
    assert "不能确定" in text
    assert "可以对照：题干对上了" not in text
    assert "苹果" in text and "红" in text


def test_duplicate_stem_uses_options_and_does_not_pick_the_other_answer():
    stem = "重复题干用于区分单选和多选时不能只看题目本身"
    single = question(
        stem=stem,
        options={"A": "苹果", "B": "香蕉", "C": "梨"},
        answer="A",
        source_row=77,
    )
    multi = question(
        qtype="multi",
        stem=stem,
        options={"A": "红", "B": "绿", "C": "蓝", "D": "黄"},
        answer="ABC",
        source_row=545,
    )
    screen = stem + "\nA. 黄\nB. 红\nC. 绿\nD. 蓝\n"
    outcome = match_text(bank(single, multi), screen)
    assert outcome.confident is True
    assert outcome.chosen is multi
    assert outcome.chosen.answer == "ABC"
    assert outcome.remapped == "BCD"
    assert "苹果" not in [text for _, text in outcome.answer_texts]
    only_single = match_text(
        bank(single, multi),
        stem + "\nA. 梨\nB. 苹果\nC. 香蕉\n",
    )
    assert only_single.chosen is single
    assert only_single.remapped == "B"
    assert only_single.answer_texts == [("A", "苹果")]


def test_numeric_option_text_remaps_100_point_zero_to_100():
    stored = question(
        stem="下列数值哪一个等于满分",
        options={"A": "100.0", "B": "60.0", "C": "0.0"},
        answer="A",
    )
    outcome = match_text(
        bank(stored),
        "下列数值哪一个等于满分\nA. 60\nB. 0\nC. 100\n",
    )
    assert outcome.confident is True
    assert outcome.remapped == "C"
    assert outcome.answer_texts == [("A", "100.0")]


def test_unmatched_options_do_not_reuse_bank_letters_as_screen_letters():
    stored = _single()
    outcome = match_text(bank(stored), "传输层的主要职责是提供端到端的可靠传输\nA. 猫\nB. 狗\nC. 鸟\nD. 鱼\n")
    assert outcome.confident is True
    assert outcome.remapped is None
    text = format_outcome(outcome)
    assert "未能对应到画面字母" in text
    assert "网页如果打乱了选项" in text
    assert "端到端可靠传输" in text


def test_partial_long_stem_can_match_and_short_fragment_cannot_be_confident():
    assert len(PARTIAL_HIGH) >= 18 and len(PARTIAL_HIGH) / len(PARTIAL_HIGH_STEM) >= 0.70
    assert 12 <= len(PARTIAL_MEDIUM) < 18 and len(PARTIAL_MEDIUM) / len(LONG) >= 0.45
    stored = question(stem=PARTIAL_HIGH_STEM, options={"A": "甲", "B": "乙", "C": "丙"}, answer="B")
    high = match_text(bank(stored), PARTIAL_HIGH)
    assert high.status == "partial"
    assert high.confident is False
    assert high.verified is False
    assert high.score > 0
    assert "片段" in format_outcome(high)
    medium_q = question(stem=LONG, options={"A": "甲", "B": "乙", "C": "丙"}, answer="A")
    medium = match_text(bank(medium_q), PARTIAL_MEDIUM)
    assert medium.status == "medium"
    assert medium.confident is False
    assert "不要把它当成唯一答案" in format_outcome(medium)
    low = match_text(bank(medium_q), LONG[:9])
    assert low.status == "low"
    assert low.confident is False
    assert low.chosen is None


def test_short_exact_stem_and_low_similarity_stay_uncertain():
    short = question(stem="网络协议", options={"A": "甲", "B": "乙", "C": "丙"}, answer="A")
    exact_short = match_text(bank(short), "网络协议")
    assert exact_short.status == "medium"
    assert exact_short.confident is False
    noisy = question(
        stem="传输层提供端到端可靠传输与差错控制功能说明",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="C",
    )
    weak = match_text(bank(noisy), "完全无关的园林绿化施工组织设计题目")
    assert weak.status == "none"
    assert weak.chosen is None
    fragment = question(
        stem="网络协议设计与实现课程的综合题干内容比较长",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="B",
    )
    listed = match_text(bank(fragment), "网络协议")
    assert listed.confident is False
    assert listed.chosen is None
    assert listed.candidates


def test_ocr_typo_on_long_unique_stem_still_finds_the_question():
    stem = "传输层提供端到端可靠传输与差错控制功能说明"
    stored = question(stem=stem, options={"A": "甲", "B": "乙", "C": "丙"}, answer="A")
    typo = "传输层提供端到端可靠传输与差错控剖功能说明"
    outcome = match_text(bank(stored), typo + "\nA. 甲\nB. 乙\nC. 丙")
    assert outcome.chosen is stored
    assert outcome.status == "high"
    assert outcome.verified is False
    assert outcome.score > 0
    assert "不是逐字确定" in format_outcome(outcome)


def test_judgment_near_duplicate_keeps_both_rows_when_answers_match():
    stem = "依据某规定工作负责人应组织执行工作票所列安全措施"
    plain = question(
        qtype="judgment",
        stem=stem,
        options={"A": "正确", "B": "错误"},
        answer="A",
        source_row=1061,
        tag="",
    )
    reserved = question(
        qtype="judgment",
        stem=stem + "（ ）",
        options={"A": "正确", "B": "错误"},
        answer="A",
        source_row=1081,
        tag="是",
    )
    assert plain.fingerprint == reserved.fingerprint
    outcome = match_text(bank(plain, reserved), stem + "\nA. 正确\nB. 错误\n")
    assert outcome.confident is False
    assert outcome.chosen is None
    assert {item.question.source_row for item in outcome.candidates} == {1061, 1081}
    text = format_outcome(outcome, stem)
    assert "不能合并成一条" in text
    assert "保命题：是" in text
    assert "保命题：（空）" in text
    assert "题库未提供解析" in text


def test_negation_and_number_changes_are_not_harmless_typos():
    stem = "工作人员不得在带电设备上作业并应立即报告负责人"
    stored = question(stem=stem, options={"A": "甲", "B": "乙", "C": "丙"}, answer="A")
    flipped = match_text(bank(stored), stem.replace("不得", "可以"))
    assert flipped.confident is False
    assert flipped.verified is False
    assert "否定" in "".join(flipped.reasons)
    bare = question(
        stem="作业人员不在带电设备上停留并应报告负责人处理",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="B",
    )
    dropped = match_text(bank(bare), "作业人员在带电设备上停留并应报告负责人处理")
    assert dropped.confident is False
    assert "不" in "".join(dropped.reasons)
    numbered = question(
        stem="距离不小于100米时应停止作业并报告现场负责人",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="C",
    )
    changed = match_text(bank(numbered), "距离不小于10米时应停止作业并报告现场负责人")
    assert changed.confident is False
    assert changed.verified is False
    assert "数字" in "".join(changed.reasons)
    swapped = question(
        stem="下列说法正确的是关于接地线装设顺序的要求说明",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="A",
    )
    wrong_word = match_text(bank(swapped), "下列说法错误的是关于接地线装设顺序的要求说明")
    assert wrong_word.confident is False
    assert "正确" in "".join(wrong_word.reasons) or "错误" in "".join(wrong_word.reasons)


def test_selected_result_still_lists_other_high_candidates_without_padding():
    from screenmatch.present import candidate_window, format_panel

    first = question(
        stem="传输层提供端到端可靠传输以及差错控制与流量控制能力说明",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="A",
        source_row=2,
    )
    second = question(
        stem="传输层提供端到端可靠传输以及差错控制与拥塞控制能力说明",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="B",
        source_row=3,
    )
    third = question(
        stem="传输层提供端到端可靠传输以及差错控制与顺序控制能力说明",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="C",
        source_row=4,
    )
    fourth = question(
        stem="完全无关的园林绿化施工组织设计与浇水养护题目内容",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="A",
        source_row=9,
    )
    outcome = match_text(bank(first, second, third, fourth), first.stem)
    assert outcome.score > 0
    assert len(outcome.candidates) >= 3
    assert len(outcome.candidates) <= 5
    assert all(item.question.source_row != 9 for item in outcome.candidates)
    assert len(candidate_window(outcome, expanded=False)) == 3
    assert len(candidate_window(outcome, expanded=True)) >= 3
    text = format_panel(outcome, expanded=False, notice="", show_current=False)
    assert "题干匹配度" in text
    assert "%" in text
    assert "传输层提供端到端可靠传输…" in text
    assert "以及差错控制与流量控制能力说明" not in text
    assert "不是正确率" not in text
    assert "解析" not in text
    assert "甲" in text or "乙" in text or "丙" in text
    if outcome.needs_review:
        assert "待确认" in text


def test_low_similarity_is_labelled_and_not_invented():
    only = question(
        stem="传输层提供端到端可靠传输与差错控制功能的完整说明文字",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="A",
    )
    outcome = match_text(bank(only), only.stem)
    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].low_match is False
    weak = match_text(bank(only), "园林绿化")
    assert weak.candidates == [] or all(item.low_match or item.score < 0.80 for item in weak.candidates)


def test_empty_bank_asks_for_excel():
    outcome = match_text(bank(), "任何题干")
    assert outcome.status == "none"
    assert "导入题库" in outcome.reasons[0]
