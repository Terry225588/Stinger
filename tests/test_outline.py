from screenmatch.geometry import rectangles_overlap
from screenmatch.outline import (
    BORDER_PX,
    MIN_INNER,
    OutlineSession,
    border_strips,
    capture_allowed,
    capture_rect,
    clamp_inner,
    drag_inner,
    hit_test,
)

SCREEN = {"left": 0, "top": 0, "width": 1920, "height": 1080}
INNER = {"left": 200, "top": 150, "width": 400, "height": 220}


def test_border_is_outside_capture_and_center_is_not_a_hit():
    strips = border_strips(INNER)
    captured = capture_rect(INNER)
    assert captured == INNER
    for strip in strips.values():
        assert rectangles_overlap(strip, captured) is False
    center_x = INNER["left"] + INNER["width"] // 2
    center_y = INNER["top"] + INNER["height"] // 2
    assert hit_test(center_x, center_y, INNER) is None
    assert hit_test(0, 0, INNER) is None
    assert hit_test(INNER["left"] + 30, INNER["top"] - BORDER_PX // 2, INNER) == "move"
    assert hit_test(INNER["left"] - BORDER_PX // 2, INNER["top"] + 40, INNER) == "w"
    assert hit_test(INNER["left"] - BORDER_PX // 2, INNER["top"] - BORDER_PX // 2, INNER) == "nw"


def test_move_and_resize_update_inner_and_keep_border_on_screen():
    moved = drag_inner(INNER, "move", 30, -20, SCREEN)
    assert moved["left"] == INNER["left"] + 30
    assert moved["top"] == INNER["top"] - 20
    assert moved["width"] == INNER["width"]
    assert capture_rect(moved)["width"] == moved["width"]
    grown = drag_inner(INNER, "se", 25, 15, SCREEN)
    assert grown["width"] == INNER["width"] + 25
    assert grown["height"] == INNER["height"] + 15
    shrunk = drag_inner(INNER, "se", -1000, -1000, SCREEN)
    assert shrunk["width"] == MIN_INNER
    assert shrunk["height"] == MIN_INNER
    shoved = drag_inner(INNER, "move", -5000, -5000, SCREEN)
    assert shoved["left"] == BORDER_PX
    assert shoved["top"] == BORDER_PX
    for strip in border_strips(shoved).values():
        assert strip["left"] >= 0
        assert strip["top"] >= 0


def test_drag_pauses_capture_and_commits_once_on_release():
    session = OutlineSession(INNER, SCREEN)
    events = []
    assert session.press(INNER["left"] + 40, INNER["top"] - 4) is True
    assert session.adjusting is True
    assert capture_allowed(adjusting=True, user_paused=False, selecting=False, overlap=False) is False
    for step in range(5):
        preview = session.motion(INNER["left"] + 40 + step, INNER["top"] - 4)
        assert preview is not None
        assert session.adjusting is True
        events.append("preview")
    committed = session.release(INNER["left"] + 80, INNER["top"] + 10)
    assert session.adjusting is False
    assert committed is not None
    assert committed != INNER
    assert session.press(INNER["left"] + INNER["width"] // 2, INNER["top"] + INNER["height"] // 2) is False
    assert len(events) == 5


def test_release_after_user_pause_does_not_resume_capture():
    assert capture_allowed(adjusting=False, user_paused=True, selecting=False, overlap=False) is False
    assert capture_allowed(adjusting=False, user_paused=False, selecting=False, overlap=False) is True
    fitted = clamp_inner({"left": 1, "top": 1, "width": 10, "height": 10}, SCREEN)
    assert fitted["width"] == MIN_INNER
    assert fitted["left"] >= BORDER_PX
