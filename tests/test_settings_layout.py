"""设置窗在默认尺寸和最小尺寸下，侧栏控件都要能点到。"""

import tkinter as tk

import pytest

PRIMARY = ("框选", "开始搜索")
ALL_CONTROLS = PRIMARY + (
    "导入题库",
    "导出模板",
    "应用快捷键",
    "用这段文字查询",
)
REMOVED = ("批量导入", "导入文件夹", "导出未匹配", "收藏本题", "移除收藏", "收藏")


def _display_or_skip():
    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.update()
        probe.destroy()
    except tk.TclError as exc:
        pytest.skip(f"没有可用的图形界面：{exc}")


def _buttons(widget) -> dict[str, tk.Widget]:
    found: dict[str, tk.Widget] = {}
    try:
        text = str(widget.cget("text"))
    except tk.TclError:
        text = ""
    if text and widget.winfo_class() in {"TButton", "Button"}:
        found[text] = widget
    for child in widget.winfo_children():
        found.update(_buttons(child))
    return found


def _box(widget) -> tuple[int, int, int, int]:
    return (
        widget.winfo_rootx(),
        widget.winfo_rooty(),
        widget.winfo_width(),
        widget.winfo_height(),
    )


def _inside(container, widget) -> bool:
    cx, cy, cw, ch = _box(container)
    x, y, w, h = _box(widget)
    if w < 24 or h < 18 or not widget.winfo_ismapped():
        return False
    return x >= cx - 1 and y >= cy - 1 and x + w <= cx + cw + 1 and y + h <= cy + ch + 1


def _reveal(app, widget) -> None:
    canvas = app.side_canvas
    canvas.update_idletasks()
    total = canvas.bbox("all")
    if not total:
        return
    span = max(total[3] - total[1], 1)
    target = widget.winfo_rooty()
    origin = canvas.winfo_rooty()
    current = canvas.canvasy(0)
    new = max(0, current + (target - origin) - 4)
    canvas.yview_moveto(min(new / span, 1))
    app.update()


def _open(size: str):
    from screenmatch.app import App

    app = App(data_dir="/tmp/stinger-layout")
    app.geometry(f"{size}+30+30")
    app.deiconify()
    app.update_idletasks()
    app.update()
    return app


@pytest.mark.parametrize("size,width,height", [("900x640", 900, 640), ("720x520", 720, 520)])
def test_settings_controls_reachable_without_growing_window(size, width, height):
    _display_or_skip()
    app = _open(size)
    try:
        assert app.winfo_width() <= width + 8
        assert app.winfo_height() <= height + 8
        buttons = _buttons(app)
        for name in REMOVED:
            assert name not in buttons
        for name in ALL_CONTROLS:
            assert name in buttons, name
            widget = buttons[name]
            assert widget.winfo_ismapped()
            assert widget.winfo_width() >= 24
            assert widget.winfo_height() >= 18
        app.side_canvas.yview_moveto(1)
        app.update()
        for name in PRIMARY:
            assert _inside(app, buttons[name]), name
            assert buttons[name].winfo_rooty() < app.side_canvas.winfo_rooty()
        app._user_paused = False
        app._selecting = False
        app._set_search_button()
        assert app.pause_btn.cget("text") == "暂停搜索"
        app._user_paused = True
        app._set_search_button()
        assert app.pause_btn.cget("text") == "开始搜索"
        app.side_canvas.yview_moveto(0)
        app.update()
        for name in ALL_CONTROLS:
            if name in PRIMARY:
                continue
            _reveal(app, buttons[name])
            assert _inside(app, buttons[name]), name
    finally:
        app.destroy()


def test_frame_and_search_colors_follow_state():
    _display_or_skip()
    from screenmatch.macui import ROLES

    app = _open("900x640")
    try:
        assert app.frame_btn.cget("bg") == ROLES["frame"]["face"]
        assert app.frame_btn.cget("fg") == ROLES["frame"]["fg"]
        assert int(app.frame_btn.cget("highlightthickness")) >= 3
        assert int(app.frame_btn.cget("borderwidth")) >= 3
        assert app.pause_btn.cget("text") == "开始搜索"
        assert app.pause_btn.cget("bg") == ROLES["start"]["face"]
        assert app.frame_ring.cget("bg") == "#000000"
        assert app.start_ring.cget("bg") == "#000000"
        assert "16" in str(app.pause_btn.cget("font"))
        app._user_paused = False
        app._selecting = False
        app._set_search_button()
        assert app.pause_btn.cget("text") == "暂停搜索"
        assert app.start_ring.cget("bg") == "#000000"
        assert app.pause_btn.cget("bg") == ROLES["pause"]["face"]
        assert app.pause_btn.cget("fg") == ROLES["pause"]["fg"]
        assert app.pause_btn.cget("activebackground") == ROLES["pause"]["pressed"]
        app.pause_btn.event_generate("<Enter>")
        assert app.pause_btn.cget("bg") == ROLES["pause"]["hover"]
        app.pause_btn.event_generate("<Leave>")
        assert app.pause_btn.cget("bg") == ROLES["pause"]["face"]
        app.pause_btn.configure(state="disabled")
        assert app.pause_btn.cget("disabledforeground") == "#555555"
        app.pause_btn.configure(state="normal")
        assert app.focus_get() is not app.panel
        from screenmatch.macui import ANSWER_RED

        assert app.panel.text.tag_cget("answer", "foreground") == ANSWER_RED
    finally:
        app.destroy()


def test_sidebar_scroll_does_not_touch_panel_activation(monkeypatch):
    _display_or_skip()
    calls: list[str] = []

    import screenmatch.app as appmod

    monkeypatch.setattr(appmod, "set_window_topmost", lambda *args, **kwargs: calls.append("top") or True)
    monkeypatch.setattr(appmod, "show_without_activating", lambda *args, **kwargs: calls.append("show") or True)
    app = appmod.App(data_dir="/tmp/stinger-layout-scroll")
    app.geometry("900x640+30+30")
    app.deiconify()
    app.update()
    calls.clear()
    try:
        app.side_canvas.yview_moveto(1)
        app.side_canvas.event_generate("<MouseWheel>", delta=-120)
        app.update()
        focus = app.focus_get()
        assert focus is not app.panel
        assert calls == []
    finally:
        app.destroy()
