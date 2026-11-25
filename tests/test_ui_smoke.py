import tkinter as tk

import pytest

from tests.helpers import question


def _display_or_skip():
    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.update()
        probe.destroy()
    except tk.TclError as exc:
        pytest.skip(f"没有可用的图形界面：{exc}")


def test_window_imports_bank_and_shows_match_without_stealing_logic(tmp_path):
    _display_or_skip()
    from openpyxl import Workbook

    from screenmatch.app import App

    path = tmp_path / "mini.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["题型", "题目", "A", "B", "C", "D", "E", "F", "答案", "难度", "试题依据", "试题解析", "保命题"])
    sheet.append(["单选题", "传输层的主要职责是提供端到端的可靠传输", "端到端可靠传输", "路由选择", "调制解调", "域名解析", "", "", "A", "", "", "", ""])
    workbook.save(path)

    app = App(data_dir=tmp_path / "data")
    app.withdraw()
    try:
        report = app.load_bank_file(path)
        assert report.valid_count == 1
        outcome = app.query_text(
            "传输层的主要职责是提供端到端的可靠传输\nA. 路由选择\nB. 端到端可靠传输\nC. 调制解调\nD. 域名解析\n"
        )
        shown = app.result.get("1.0", "end")
        assert outcome.remapped == "B"
        assert "端到端可靠传输" in shown
        assert "按当前画面选项对应的字母：B" in shown
        assert "题库未提供解析" in shown
        app.update_idletasks()
        app.panel.deiconify()
        app.panel.update_idletasks()
        assert app.panel.winfo_exists()
        assert 200 < app.panel.winfo_width() < 700
        app._user_paused = False
        app.watch.resume()
        app._region = {"left": 0, "top": 900, "width": 40, "height": 40}
        app._toggle_pause()
        cleared = app.panel.text.get("1.0", "end")
        assert "已暂停" in cleared
        assert "端到端可靠传输" not in cleared
        assert app.panel.text.tag_cget("answer", "foreground") == "#c62828"
        assert app._watch_thread is None
    finally:
        app.destroy()


def test_question_helper_builds_fingerprint():
    item = question(stem="只是为了确认夹具", options={"A": "甲", "B": "乙", "C": "丙"}, answer="A")
    assert item.fingerprint
