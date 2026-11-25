"""识别区的可见边框。边框在内容区外面，中间没有窗口。

不使用透明色键，也不给整块屏幕加 WS_EX_TRANSPARENT。
中间能点到网页，是因为那里没有我们的窗口，不是因为把桌面做成穿透。
自动摆放边框时不激活窗口。用户自己按住边框拖动时，网页仍可能收到鼠标离开；程序不把焦点送回去。
"""

from __future__ import annotations

import tkinter as tk

BORDER_PX = 12
MIN_INNER = 48
_WATCH_COLOR = "#000000"
_PAUSE_COLOR = "#4A4A4A"


def outer_frame(inner: dict, border: int = BORDER_PX) -> dict:
    return {
        "left": int(inner["left"]) - border,
        "top": int(inner["top"]) - border,
        "width": int(inner["width"]) + 2 * border,
        "height": int(inner["height"]) + 2 * border,
    }


def capture_rect(inner: dict) -> dict:
    return {
        "left": int(inner["left"]),
        "top": int(inner["top"]),
        "width": int(inner["width"]),
        "height": int(inner["height"]),
    }


def border_strips(inner: dict, border: int = BORDER_PX) -> dict[str, dict]:
    """四条边。左右条不包含角，角算在上下条里。都不与内容区重叠。"""
    left = int(inner["left"])
    top = int(inner["top"])
    width = int(inner["width"])
    height = int(inner["height"])
    return {
        "top": {
            "left": left - border,
            "top": top - border,
            "width": width + 2 * border,
            "height": border,
        },
        "bottom": {
            "left": left - border,
            "top": top + height,
            "width": width + 2 * border,
            "height": border,
        },
        "left": {"left": left - border, "top": top, "width": border, "height": height},
        "right": {"left": left + width, "top": top, "width": border, "height": height},
    }


def hit_test(x: int, y: int, inner: dict, border: int = BORDER_PX) -> str | None:
    """内容区返回 None，让点击落到底下的窗口。框外也返回 None。"""
    outer = outer_frame(inner, border)
    if x < outer["left"] or y < outer["top"]:
        return None
    if x >= outer["left"] + outer["width"] or y >= outer["top"] + outer["height"]:
        return None
    if (
        inner["left"] <= x < inner["left"] + inner["width"]
        and inner["top"] <= y < inner["top"] + inner["height"]
    ):
        return None
    near_left = x < outer["left"] + border
    near_right = x >= outer["left"] + outer["width"] - border
    near_top = y < outer["top"] + border
    near_bottom = y >= outer["top"] + outer["height"] - border
    if near_top and near_left:
        return "nw"
    if near_top and near_right:
        return "ne"
    if near_bottom and near_left:
        return "sw"
    if near_bottom and near_right:
        return "se"
    if near_top:
        return "move"
    if near_bottom:
        return "s"
    if near_left:
        return "w"
    if near_right:
        return "e"
    return None


def clamp_inner(inner: dict, screen: dict, border: int = BORDER_PX, min_size: int = MIN_INNER) -> dict:
    screen_left = int(screen.get("left", 0))
    screen_top = int(screen.get("top", 0))
    max_width = int(screen["width"]) - 2 * border
    max_height = int(screen["height"]) - 2 * border
    width = max(min_size, min(int(inner["width"]), max_width))
    height = max(min_size, min(int(inner["height"]), max_height))
    left = int(inner["left"])
    top = int(inner["top"])
    left = max(left, screen_left + border)
    top = max(top, screen_top + border)
    left = min(left, screen_left + int(screen["width"]) - border - width)
    top = min(top, screen_top + int(screen["height"]) - border - height)
    return {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}


def drag_inner(
    start: dict,
    mode: str,
    dx: int,
    dy: int,
    screen: dict,
    border: int = BORDER_PX,
    min_size: int = MIN_INNER,
) -> dict:
    left = int(start["left"])
    top = int(start["top"])
    width = int(start["width"])
    height = int(start["height"])
    if mode == "move":
        left += dx
        top += dy
    elif mode == "e":
        width += dx
    elif mode == "s":
        height += dy
    elif mode == "w":
        left += dx
        width -= dx
    elif mode == "n":
        top += dy
        height -= dy
    elif mode == "ne":
        top += dy
        height -= dy
        width += dx
    elif mode == "nw":
        left += dx
        width -= dx
        top += dy
        height -= dy
    elif mode == "se":
        width += dx
        height += dy
    elif mode == "sw":
        left += dx
        width -= dx
        height += dy
    return clamp_inner(
        {"left": left, "top": top, "width": width, "height": height},
        screen,
        border,
        min_size,
    )


def capture_allowed(*, adjusting: bool, user_paused: bool, selecting: bool, overlap: bool) -> bool:
    return not (adjusting or user_paused or selecting or overlap)


class OutlineSession:
    """拖动期间不更新已提交的截图区。松开才提交。"""

    def __init__(self, inner: dict, screen: dict) -> None:
        self.inner = clamp_inner(inner, screen)
        self.screen = screen
        self.adjusting = False
        self._mode: str | None = None
        self._origin: tuple[int, int] | None = None
        self._start: dict | None = None

    def press(self, x: int, y: int) -> bool:
        zone = hit_test(x, y, self.inner)
        if zone is None:
            return False
        self.adjusting = True
        self._mode = zone
        self._origin = (x, y)
        self._start = dict(self.inner)
        return True

    def motion(self, x: int, y: int) -> dict | None:
        if not self.adjusting or self._origin is None or self._start is None or self._mode is None:
            return None
        self.inner = drag_inner(
            self._start,
            self._mode,
            x - self._origin[0],
            y - self._origin[1],
            self.screen,
        )
        return dict(self.inner)

    def release(self, x: int, y: int) -> dict | None:
        if not self.adjusting:
            return None
        moved = self.motion(x, y)
        self.adjusting = False
        self._mode = None
        self._origin = None
        self._start = None
        return moved


class BorderOverlay:
    """四条可见边。内容区没有控件，因此点击会落到下面的窗口。"""

    def __init__(self, master, inner: dict, screen: dict, on_adjust_start, on_adjust_end, paused: bool = False) -> None:
        self.master = master
        self.screen = screen
        self.session = OutlineSession(inner, screen)
        self.on_adjust_start = on_adjust_start
        self.on_adjust_end = on_adjust_end
        self.alive = True
        self._paused = paused
        self._strips: dict[str, tk.Toplevel] = {}
        self._pressed = False
        from screenmatch.winfocus import mark_quiet_window

        for name in ("top", "bottom", "left", "right"):
            strip = tk.Toplevel(master)
            strip.withdraw()
            strip.overrideredirect(True)
            mark_quiet_window(strip, tool=True)
            strip.configure(bg=_PAUSE_COLOR if paused else _WATCH_COLOR)
            if name == "top":
                label = tk.Label(
                    strip,
                    text="已暂停" if paused else "识别区",
                    bg=strip.cget("bg"),
                    fg="#fffdf8",
                    font=("TkDefaultFont", 8),
                )
                label.pack(fill=tk.BOTH, expand=True)
                label.bind("<ButtonPress-1>", self._press)
                label.bind("<B1-Motion>", self._motion)
                label.bind("<ButtonRelease-1>", self._release)
                strip._caption = label  # type: ignore[attr-defined]
            strip.bind("<ButtonPress-1>", self._press)
            strip.bind("<B1-Motion>", self._motion)
            strip.bind("<ButtonRelease-1>", self._release)
            self._strips[name] = strip
        self.place()
        for strip in self._strips.values():
            self._raise_strip(strip)

    def place(self) -> None:
        from screenmatch.winfocus import position_without_activating, set_window_topmost, show_without_activating

        for name, rect in border_strips(self.session.inner).items():
            strip = self._strips[name]
            position_without_activating(
                strip, rect["width"], rect["height"], rect["left"], rect["top"]
            )
            if not strip.winfo_viewable():
                show_without_activating(strip, tool=True)
            set_window_topmost(strip, True)

    def set_inner(self, inner: dict) -> None:
        self.session.inner = clamp_inner(inner, self.screen)
        if self.alive:
            self.place()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        color = _PAUSE_COLOR if paused else _WATCH_COLOR
        text = "已暂停" if paused else "识别区"
        for strip in self._strips.values():
            strip.configure(bg=color)
            caption = getattr(strip, "_caption", None)
            if caption is not None:
                caption.configure(bg=color, text=text)

    def destroy(self) -> None:
        self.alive = False
        for strip in self._strips.values():
            try:
                strip.destroy()
            except tk.TclError:
                pass
        self._strips.clear()

    def _raise_strip(self, strip) -> None:
        from screenmatch.winfocus import detach_from_owner, set_window_topmost

        try:
            strip.update_idletasks()
        except tk.TclError:
            return
        detach_from_owner(strip)
        set_window_topmost(strip, True)

    def _press(self, event) -> None:
        if not self.session.press(int(event.x_root), int(event.y_root)):
            return
        self._pressed = True
        self.on_adjust_start()

    def _motion(self, event) -> None:
        if not self._pressed:
            return
        moved = self.session.motion(int(event.x_root), int(event.y_root))
        if moved is not None:
            self.place()

    def _release(self, event) -> None:
        if not self._pressed:
            return
        committed = self.session.release(int(event.x_root), int(event.y_root))
        self._pressed = False
        self.place()
        if committed is not None:
            self.on_adjust_end(committed)
