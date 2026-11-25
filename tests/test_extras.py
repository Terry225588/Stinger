from screenmatch.bank import BankCatalog, format_batch_report
from screenmatch.hotkeys import (
    DEFAULT_FRAME,
    WM_HOTKEY,
    parse_accelerator,
    poll_hotkey_ids,
    register_hotkey,
)
from screenmatch.match import match_text
from screenmatch.present import shows_current_answer
from screenmatch.recognition import is_same_recognition, recognition_key
from tests.helpers import bank, question
from tests.test_import import _book


def test_hotkey_parser_and_register_is_not_a_keyboard_hook():
    parsed = parse_accelerator(DEFAULT_FRAME)
    assert parsed is not None
    sequence, mods, vk = parsed
    assert sequence == "<Control-Alt-f>"
    assert vk == ord("F")
    assert parse_accelerator("没有修饰键") is None

    class User32:
        def __init__(self) -> None:
            self.registered = []
            self.hooks = []

        def RegisterHotKey(self, hwnd, hotkey_id, modifiers, virtual_key):
            self.registered.append((hwnd, hotkey_id, modifiers, virtual_key))
            return 1

        def SetWindowsHookExW(self, *args):
            self.hooks.append(args)
            return 1

    user32 = User32()
    assert register_hotkey(user32, 7, 1, mods, vk) is True
    assert user32.registered == [(7, 1, mods, vk)]
    assert user32.hooks == []

    class Message:
        def __init__(self) -> None:
            self.wParam = 0

    class Poller:
        def __init__(self) -> None:
            self.left = [1, 2]

        def MSG(self):
            return Message()

        def PeekMessageW(self, message, hwnd, first, last, remove):
            assert first == last == WM_HOTKEY
            if not self.left:
                return 0
            message.wParam = self.left.pop(0)
            return 1

    assert poll_hotkey_ids(Poller(), 7) == [1, 2]


def test_unchanged_recognition_skips_equivalent_text():
    first = recognition_key("传输层 负责端到端可靠传输。")
    assert is_same_recognition(first, "传输层负责端到端可靠传输")
    assert not is_same_recognition(first, "传输层负责路由选择而不是端到端")
    assert not is_same_recognition(None, "传输层负责端到端可靠传输")


def test_low_or_conflict_is_not_a_hard_answer():
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
    outcome = match_text(bank(first, second), "传输层提供端到端可靠传输")
    assert shows_current_answer(outcome) is False
    from screenmatch.present import format_panel

    panel = format_panel(outcome, expanded=False, notice="", show_current=True)
    assert "待确认" in panel


def test_one_file_uses_single_import_and_many_report_each(tmp_path):
    import tkinter as tk

    import pytest

    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.update()
        probe.destroy()
    except tk.TclError as exc:
        pytest.skip(f"没有可用的图形界面：{exc}")
    from screenmatch.app import App

    one = tmp_path / "甲库.xlsx"
    two = tmp_path / "乙库.xlsx"
    _book(
        [["单选题", "【示例】第一份导入题干足够长", "甲", "乙", "丙", "", "", "", "A", "", "", "", ""]],
        one,
    )
    _book(
        [["单选题", "【示例】第二份导入题干足够长", "甲", "乙", "丙", "", "", "", "B", "", "", "", ""]],
        two,
    )
    app = App(data_dir=tmp_path / "data")
    app.withdraw()
    try:
        app.import_selected_files([one])
        assert app.catalog.mode == "甲库"
        assert "已导入「甲库」" in app.status.get()
        app.catalog.use("全部题库")
        report = app.import_selected_files([one, two])
        assert report is not None
        assert "甲库.xlsx：成功 1 题" in report
        assert "乙库.xlsx：成功 1 题" in report
        assert app.catalog.mode == "全部题库"
        assert {question.bank_name for question in app.bank.questions} == {"甲库", "乙库"}
    finally:
        app.destroy()


def test_batch_import_reports_each_file_and_keeps_all_banks_mode(tmp_path):
    good = tmp_path / "安全生产.xlsx"
    bad = tmp_path / "坏表.xlsx"
    _book(
        [["单选题", "【示例】批量导入的单选题干足够长", "甲", "乙", "丙", "", "", "", "A", "", "", "", ""]],
        good,
    )
    bad.write_bytes(b"not a workbook")
    catalog = BankCatalog()
    catalog.use("全部题库")
    results = catalog.add_files([good, bad])
    report = format_batch_report(results)
    assert "安全生产.xlsx：成功 1 题" in report
    assert "坏表.xlsx：失败" in report
    assert catalog.mode == "全部题库"
    assert catalog.active().questions[0].bank_name == "安全生产"
    catalog.save(tmp_path / "data")
    loaded = BankCatalog.load(tmp_path / "data")
    assert loaded.mode == "全部题库"
    loaded.use("安全生产")
    loaded.save(tmp_path / "data")
    assert BankCatalog.load(tmp_path / "data").mode == "安全生产"
