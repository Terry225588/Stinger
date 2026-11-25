"""自动识别刷新不得激活窗口。框选遮罩仍然会拿走焦点，这是用户自己在拖。"""

from screenmatch.app import dispatch_watch_event
from screenmatch.display_state import AnswerBoard
from screenmatch.match import match_text
from screenmatch.winfocus import (
    SW_SHOWNOACTIVATE,
    SWP_NOACTIVATE,
    SWP_NOOWNERZORDER,
    WS_EX_APPWINDOW,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    _MOVE_FLAGS,
    prepare_quiet_window,
    reveal_quiet,
)
from tests.helpers import bank, question


class _QuietUser32:
    def __init__(self) -> None:
        self.style = 0
        self.shown: list[int] = []
        self.flags: list[int] = []
        self.foreground: list[str] = []

    def GetWindowLongPtrW(self, hwnd, index):
        return self.style

    def SetWindowLongPtrW(self, hwnd, index, value):
        self.style = int(value)
        return self.style

    def SetWindowPos(self, hwnd, insert_after, x, y, cx, cy, flags):
        self.flags.append(int(flags))
        return 1

    def ShowWindow(self, hwnd, cmd):
        self.shown.append(int(cmd))
        return 1

    def SetForegroundWindow(self, hwnd):
        self.foreground.append("foreground")
        return 1


def test_quiet_style_uses_noactivate_and_not_foreground():
    user32 = _QuietUser32()
    border = prepare_quiet_window(user32, 11, tool=True)
    reveal_quiet(user32, 11)
    assert border & WS_EX_NOACTIVATE
    assert border & WS_EX_TOOLWINDOW
    assert not border & WS_EX_APPWINDOW
    panel = prepare_quiet_window(user32, 12, taskbar=True)
    assert panel & WS_EX_NOACTIVATE
    assert panel & WS_EX_APPWINDOW
    assert not panel & WS_EX_TOOLWINDOW
    assert user32.shown == [SW_SHOWNOACTIVATE]
    assert user32.foreground == []
    assert user32.flags
    assert all(flags & SWP_NOACTIVATE for flags in user32.flags)
    assert all(flags & SWP_NOOWNERZORDER for flags in user32.flags)
    assert _MOVE_FLAGS & SWP_NOACTIVATE
    assert _MOVE_FLAGS & SWP_NOOWNERZORDER


def test_watch_refresh_does_not_activate_panel():
    class Status:
        def __init__(self) -> None:
            self.values: list[str] = []

        def set(self, value: str) -> None:
            self.values.append(value)

    class Panel:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def render(self) -> None:
            self.calls.append("render")

        def lift(self) -> None:
            self.calls.append("lift")

        def focus_force(self) -> None:
            self.calls.append("focus_force")

        def deiconify(self) -> None:
            self.calls.append("deiconify")

        def grab_set(self) -> None:
            self.calls.append("grab_set")

    class Host:
        def __init__(self) -> None:
            self.status = Status()
            self.panel = Panel()
            self.board = AnswerBoard()
            self.shown: list[str] = []

        def _invalidate(self, reason: str) -> None:
            self.board.invalidate(reason)
            self.panel.render()

        def _show_text(self, content: str, status: str) -> None:
            self.shown.append(status)

    host = Host()
    item = question(
        stem="传输层负责端到端可靠传输以及差错控制",
        options={"A": "可靠传输", "B": "路由选择", "C": "域名解析"},
        answer="A",
    )
    outcome = match_text(bank(item), "传输层负责端到端可靠传输以及差错控制")
    dispatch_watch_event(host, ("status", "正在识别…"))
    dispatch_watch_event(host, ("result", "传输层负责端到端可靠传输以及差错控制", outcome))
    dispatch_watch_event(host, ("invalid", "这一帧没有识别到文字。上一题答案已作废。"))
    assert host.panel.calls
    assert set(host.panel.calls) == {"render"}
    assert "识别完成。答案在浮动面板。" in host.status.values
    assert host.board.outcome is None


def test_region_select_still_takes_focus_on_purpose():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "src" / "screenmatch" / "region_select.py").read_text(
        encoding="utf-8"
    )
    assert "focus_force" in text
    assert "grab_set" in text
