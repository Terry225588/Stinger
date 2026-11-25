from screenmatch.display_state import AnswerBoard
from screenmatch.geometry import rectangles_overlap
from screenmatch.match import match_text
from tests.helpers import bank, question


def test_stale_answer_is_cleared_on_pause_mismatch_and_empty():
    stored = question(
        stem="传输层提供端到端可靠传输与差错控制功能说明",
        options={"A": "甲", "B": "乙", "C": "丙"},
        answer="A",
    )
    board = AnswerBoard()
    board.apply_match(match_text(bank(stored), stored.stem))
    assert board.show_current is True
    assert board.outcome is not None
    assert board.outcome.verified is True

    board.invalidate("已暂停。上一题答案已作废，不再当作当前题。")
    assert board.show_current is False
    assert board.outcome is None
    assert "作废" in board.notice

    board.apply_match(match_text(bank(stored), stored.stem))
    assert board.show_current is True
    flipped = match_text(bank(stored), stored.stem.replace("与", "和"))
    board.apply_match(flipped)
    if flipped.status != "high" or flipped.needs_review:
        assert board.show_current is False
        assert board.notice == "待确认"
    else:
        assert board.outcome is flipped

    partial = match_text(bank(stored), stored.stem[:20])
    board.apply_match(partial)
    assert board.show_current is False
    assert board.outcome is not None
    assert board.notice == "待确认"

    board.invalidate("这一帧没有识别到文字。上一题答案已作废。")
    assert board.outcome is None
    assert "没有识别到文字" in board.notice


def test_topmost_off_clears_instead_of_returning():
    import screenmatch.winfocus as winfocus

    calls = []

    class Widget:
        def attributes(self, key, value=None):
            calls.append((key, value))

    original = winfocus.os.name
    winfocus.os.name = "posix"
    try:
        assert winfocus.set_window_topmost(Widget(), True) is True
        assert winfocus.set_window_topmost(Widget(), False) is True
    finally:
        winfocus.os.name = original
    assert calls == [("-topmost", True), ("-topmost", False)]


def test_topmost_handles_are_pointer_sized_all_ones():
    import ctypes

    from screenmatch.winfocus import handle_bits, insert_after_handle

    top = insert_after_handle(True)
    not_top = insert_after_handle(False)
    bits = ctypes.sizeof(ctypes.c_void_p) * 8
    assert ctypes.sizeof(top) == ctypes.sizeof(ctypes.c_void_p)
    assert handle_bits(top) == (1 << bits) - 1
    assert handle_bits(not_top) == (1 << bits) - 2


def test_place_topmost_checks_style_bit_and_uses_pointer_handles():
    from screenmatch.winfocus import WS_EX_TOPMOST, handle_bits, insert_after_handle, place_topmost

    class User32:
        def __init__(self) -> None:
            self.calls = []
            self.flags = []
            self.styles: dict[int, int] = {}

        def SetWindowPos(self, hwnd, insert_after, x, y, cx, cy, flags):
            self.calls.append(handle_bits(insert_after))
            self.flags.append(flags)
            enabled = handle_bits(insert_after) == handle_bits(insert_after_handle(True))
            self.styles[handle_bits(hwnd)] = WS_EX_TOPMOST if enabled else 0
            return 1

        def GetWindowLongPtrW(self, hwnd, index):
            return self.styles.get(handle_bits(hwnd), 0)

    user32 = User32()
    hwnd = insert_after_handle(False)
    assert place_topmost(user32, hwnd, True) is True
    assert place_topmost(user32, hwnd, False) is True
    assert user32.calls == [
        handle_bits(insert_after_handle(True)),
        handle_bits(insert_after_handle(False)),
    ]
    from screenmatch.winfocus import SWP_NOACTIVATE, SWP_NOOWNERZORDER

    assert user32.flags
    assert all(flags & SWP_NOACTIVATE for flags in user32.flags)
    assert all(flags & SWP_NOOWNERZORDER for flags in user32.flags)


def test_rectangles_overlap_detects_panel_covering_region():
    region = {"left": 100, "top": 100, "width": 400, "height": 200}
    panel = {"left": 450, "top": 250, "width": 200, "height": 200}
    outside = {"left": 800, "top": 100, "width": 200, "height": 200}
    assert rectangles_overlap(region, panel) is True
    assert rectangles_overlap(region, outside) is False
