from screenmatch.normalize import normalize_match_text, stem_fingerprint


def test_empty_brackets_whitespace_and_punctuation_do_not_change_stem():
    bare = "下列说法正确的是"
    variants = [
        "下列说法正确的是（）",
        "下列说法正确的是()",
        "下列说法正确的是（ ）",
        "下列说法正确的是【】",
        "  下列说法正确的是 ？ ",
        "下列说法正确的是[]",
    ]
    expected = stem_fingerprint(bare)
    assert expected
    for variant in variants:
        assert stem_fingerprint(variant) == expected


def test_numeric_option_100_matches_100_point_zero():
    assert normalize_match_text("100.0") == normalize_match_text("100")
    assert normalize_match_text("100.00") == "100"
    assert normalize_match_text("１００．０") == "100"
    assert normalize_match_text("100.5") == normalize_match_text("100.50")
    assert normalize_match_text("100.0") != normalize_match_text("1000")


def test_leading_index_and_type_mark_are_removed_but_decimal_stem_is_kept():
    assert stem_fingerprint("12. 传输层负责端到端传输") == stem_fingerprint("传输层负责端到端传输")
    assert stem_fingerprint("【单选题】传输层负责端到端传输") == stem_fingerprint("传输层负责端到端传输")
    assert stem_fingerprint("单选题 传输层负责端到端传输") == stem_fingerprint("传输层负责端到端传输")
    assert stem_fingerprint("单选题库如何建设才能保证题目质量") != stem_fingerprint("库如何建设才能保证题目质量")
    assert stem_fingerprint("（3）传输层负责端到端传输") == stem_fingerprint("传输层负责端到端传输")
    assert stem_fingerprint("100.0是一个合法数值") == stem_fingerprint("100是一个合法数值")


def test_nonempty_brackets_keep_inner_text():
    assert stem_fingerprint("说法是（正确）") == stem_fingerprint("说法是正确")


def test_analysis_placeholder_is_empty():
    from screenmatch.normalize import clean_analysis

    assert clean_analysis("无") == ""
    assert clean_analysis("【无】") == ""
    assert clean_analysis(None) == ""
    assert clean_analysis("见教材第 3 章") == "见教材第 3 章"
