from screenmatch.ocr_text import join_ocr_lines, parse_ocr_text


def test_parse_multiline_options_and_ignore_empty_brackets():
    parsed = parse_ocr_text(
        "3. 下列说法正确的是（）\nA. 100\nB. 200\nC. 300\nD. 400\n上一题\n"
    )
    assert "下列说法正确的是" in parsed.stem
    assert parsed.options == {"A": "100", "B": "200", "C": "300", "D": "400"}
    assert "（）" not in parsed.fingerprint
    assert "上一题" not in parsed.stem


def test_parse_inline_fullwidth_and_six_options():
    inline = parse_ocr_text("分组交换有哪些特点 A、存储转发 B、独占电路 C、统计复用 D、逐段链路")
    assert list(inline.options) == list("ABCD")
    assert inline.options["A"] == "存储转发"
    assert "分组交换" in inline.stem
    wide = parse_ocr_text("题干写在前面\nＡ．甲\nＢ．乙\nＣ．丙\n")
    assert wide.options["A"] == "甲"
    assert wide.options["C"] == "丙"
    six = parse_ocr_text(
        "六个选项的题目正文\nA. 一\nB. 二\nC. 三\nD. 四\nE. 五\nF. 六\n"
    )
    assert list(six.options) == list("ABCDEF")


def test_joined_option_line_and_judgment_without_letters():
    joined = parse_ocr_text("题干在同一行 A. 甲 B. 乙 C. 丙 D. 丁")
    assert joined.options == {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}
    judged = parse_ocr_text("操作系统是否属于系统软件\n错误\n正确\n")
    assert judged.options == {"A": "错误", "B": "正确"}
    assert "操作系统" in judged.stem


def test_numeric_display_is_not_rewritten_by_the_parser():
    parsed = parse_ocr_text("满分是多少\nA. 100.0\nB. 60\nC. 0\n")
    assert parsed.options["A"] == "100.0"
    assert parsed.options["B"] == "60"


def test_join_ocr_boxes_into_reading_order():
    result = [
        [[[0, 40], [20, 40], [20, 55], [0, 55]], "A. 甲", 0.9],
        [[[0, 0], [80, 0], [80, 16], [0, 16]], "题干", 0.99],
        [[[90, 42], [120, 42], [120, 56], [90, 56]], "B. 乙", 0.9],
    ]
    text = join_ocr_lines(result)
    assert text.splitlines() == ["题干", "A. 甲 B. 乙"]
