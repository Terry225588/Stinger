from screenmatch.bank import ALL_BANKS, BankCatalog
from screenmatch.match import match_stem_prefix, match_text
from screenmatch.present import format_outcome, format_panel
from tests.helpers import bank, question
from tests.test_import import _book


STEM = "传输层提供端到端可靠传输以及差错控制说明文字"


def test_prefix_under_ten_characters_does_not_guess():
    item = question(stem=STEM, options={"A": "可靠传输", "B": "路由选择", "C": "域名解析"}, answer="A")
    assert match_stem_prefix(bank(item), "传输层提供端到端可") is None


def test_unique_prefix_of_ten_characters_can_show_that_question():
    item = question(stem=STEM, options={"A": "可靠传输", "B": "路由选择", "C": "域名解析"}, answer="A")
    outcome = match_stem_prefix(bank(item), "传输层提供端到端可靠")
    assert outcome is not None
    assert outcome.needs_more is False
    assert outcome.chosen is item
    panel = format_panel(outcome, expanded=False, notice="", show_current=False)
    assert "可靠传输" in panel
    assert "待确认" in panel


def test_shared_prefix_with_different_answers_waits_for_more_text():
    first = question(
        stem="传输层提供端到端可靠传输以及差错控制说明文字",
        options={"A": "差错控制", "B": "路由选择", "C": "域名解析"},
        answer="A",
    )
    second = question(
        stem="传输层提供端到端可靠传输以及流量控制说明文字",
        options={"A": "域名解析", "B": "流量控制", "C": "路由选择"},
        answer="B",
        source_row=3,
    )
    outcome = match_stem_prefix(bank(first, second), "传输层提供端到端可靠")
    assert outcome is not None
    assert outcome.needs_more is True
    assert outcome.chosen is None
    assert outcome.verified is False
    answers = {item.question.answer for item in outcome.candidates}
    assert answers == {"A", "B"}


def test_judgment_panel_shows_right_or_wrong_not_letters():
    item = question(
        qtype="judgment",
        stem="操作系统属于系统软件这一判断题干足够长",
        options={"A": "正确", "B": "错误"},
        answer="A",
    )
    screen = "操作系统属于系统软件这一判断题干足够长\nA. 错误\nB. 正确\n"
    outcome = match_text(bank(item), screen)
    panel = format_panel(outcome, expanded=False, notice="", show_current=True)
    detail = format_outcome(outcome, screen)
    assert "对" in panel
    assert "题库 A" not in panel
    assert "画面 B" not in panel
    assert "题库记录的字母" not in detail
    assert "\n对\n" in detail or detail.strip().splitlines().count("对") >= 1


def test_catalog_names_switch_and_keeps_conflicts(tmp_path):
    stem = "同一题干在两个题库里答案并不相同需要分开"
    alpha = tmp_path / "安全生产.xlsx"
    beta = tmp_path / "交通法规.xlsx"
    _book(
        [["单选题", stem, "甲答案", "乙答案", "丙答案", "", "", "", "A", "", "", "", ""]],
        alpha,
    )
    _book(
        [["单选题", stem, "甲答案", "乙答案", "丙答案", "", "", "", "C", "", "", "", ""]],
        beta,
    )
    catalog = BankCatalog()
    catalog.add_file(alpha)
    catalog.add_file(beta)
    assert catalog.names() == ["交通法规", "安全生产"]

    catalog.use("安全生产")
    one = match_text(catalog.active(), stem)
    assert one.chosen is not None
    assert one.chosen.answer == "A"
    assert one.chosen.bank_name == "安全生产"

    catalog.use("交通法规")
    other = match_text(catalog.active(), stem)
    assert other.chosen is not None
    assert other.chosen.answer == "C"

    catalog.use(ALL_BANKS)
    both = match_text(catalog.active(), stem)
    assert both.chosen is None
    assert {item.question.bank_name for item in both.candidates} == {"安全生产", "交通法规"}
    panel = format_panel(both, expanded=True, notice="", show_current=False)
    assert "安全生产" in panel
    assert "交通法规" in panel
    assert "待确认" in panel

    catalog.save(tmp_path / "data")
    loaded = BankCatalog.load(tmp_path / "data")
    assert loaded.names() == ["交通法规", "安全生产"]
    assert loaded.mode == ALL_BANKS


def test_icon_file_is_the_supplied_artwork():
    from pathlib import Path

    from PIL import Image

    root = Path(__file__).resolve().parents[1]
    jpg = root / "assets" / "stinger-app-icon.jpg"
    ico = root / "assets" / "stinger.ico"
    assert jpg.is_file()
    assert ico.is_file()
    with Image.open(jpg) as image:
        assert image.size[0] >= 64
        assert image.mode in {"RGB", "RGBA"}
    with Image.open(ico) as image:
        assert image.format == "ICO"
        assert image.size[0] >= 16
