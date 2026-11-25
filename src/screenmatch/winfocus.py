"""把可见窗口置顶或取消置顶，并且不激活它。

Windows 10 x64 上，HWND 和 HWND_TOPMOST 都是指针宽度。
不声明参数类型时，ctypes 可能把 -1 截成 32 位，SetWindowPos 就不会设置
WS_EX_TOPMOST。这里用指针宽度的原型，并核对扩展样式位。

这不是隐藏窗口，也不伪造焦点。
"""

from __future__ import annotations

import os
import sys

WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20
GA_ROOT = 2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020
SWP_NOOWNERZORDER = 0x0200
SW_SHOWNOACTIVATE = 4
# 不改大小和位置。NOOWNERZORDER 避免把设置窗一起带到网页前面。
_SWP_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_NOOWNERZORDER
# 只改位置和大小，不改变叠放，也不激活。
_MOVE_FLAGS = SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER
_STYLE_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_FRAMECHANGED


def insert_after_handle(enabled: bool):
    """HWND_TOPMOST (-1) 或 HWND_NOTOPMOST (-2)，宽度与指针一致。"""
    import ctypes

    return ctypes.c_void_p(-1 if enabled else -2)


def handle_bits(handle) -> int:
    import ctypes

    value = ctypes.cast(handle, ctypes.c_void_p).value
    if value is None:
        return 0
    return int(value)


def enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return


def bind_user32():
    """声明 64 位安全的 user32 原型。只在 Windows 上调用。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd_type = wintypes.HWND
    user32.GetAncestor.argtypes = [hwnd_type, wintypes.UINT]
    user32.GetAncestor.restype = hwnd_type
    user32.GetParent.argtypes = [hwnd_type]
    user32.GetParent.restype = hwnd_type
    user32.IsWindow.argtypes = [hwnd_type]
    user32.IsWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        hwnd_type,
        hwnd_type,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [hwnd_type, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    long_ptr = ctypes.c_ssize_t
    get_long = getattr(user32, "GetWindowLongPtrW", None)
    if get_long is None:
        get_long = user32.GetWindowLongW
    get_long.argtypes = [hwnd_type, ctypes.c_int]
    get_long.restype = long_ptr
    user32.GetWindowLongPtrW = get_long
    set_long = getattr(user32, "SetWindowLongPtrW", None)
    if set_long is None:
        set_long = user32.SetWindowLongW
    set_long.argtypes = [hwnd_type, ctypes.c_int, long_ptr]
    set_long.restype = long_ptr
    user32.SetWindowLongPtrW = set_long
    return user32


def _as_hwnd(value):
    import ctypes
    from ctypes import wintypes

    if value is None:
        return None
    if isinstance(value, wintypes.HWND):
        return value
    number = int(value)
    if number == 0:
        return None
    return wintypes.HWND(number)


def toplevel_hwnds(user32, widget_hwnd):
    """Tk 的 winfo_id 常常是客户区子窗口。置顶必须打在外壳顶层窗口上。"""
    from ctypes import wintypes

    raw = _as_hwnd(widget_hwnd)
    if raw is None:
        return []
    found = []
    seen: set[int] = set()

    def add(item) -> None:
        handle = _as_hwnd(item)
        if handle is None:
            return
        key = handle_bits(handle)
        if key == 0 or key in seen:
            return
        if not user32.IsWindow(handle):
            return
        seen.add(key)
        found.append(handle)

    root = user32.GetAncestor(raw, GA_ROOT)
    add(root)
    parent = user32.GetParent(raw)
    add(parent)
    add(raw)
    return found


def exstyle(user32, hwnd) -> int:
    return int(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE))


def is_topmost_hwnd(user32, hwnd) -> bool:
    return bool(exstyle(user32, hwnd) & WS_EX_TOPMOST)


_last_topmost_error = 0


def last_topmost_error() -> int:
    """最近一次 SetWindowPos 失败时的 Win32 错误码。成功时为 0。"""
    return _last_topmost_error


def place_topmost(user32, hwnd, enabled: bool) -> bool:
    import ctypes

    global _last_topmost_error
    insert_after = insert_after_handle(enabled)
    # c_void_p 与 HWND 同为指针宽度。不要把 -1 当成 32 位整数传入。
    ok = user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, _SWP_FLAGS)
    if not ok:
        _last_topmost_error = int(ctypes.get_last_error())
        return False
    matched = is_topmost_hwnd(user32, hwnd) if enabled else not is_topmost_hwnd(user32, hwnd)
    _last_topmost_error = 0 if matched else int(ctypes.get_last_error())
    return matched


def widget_hwnd_value(widget) -> int:
    widget.update_idletasks()
    return int(widget.winfo_id())


def set_window_topmost(widget, enabled: bool) -> bool:
    """置顶或取消置顶。取消时必须清掉 WS_EX_TOPMOST。失败则返回 False。"""
    if os.name != "nt":
        try:
            widget.attributes("-topmost", bool(enabled))
        except Exception:
            return False
        return True
    user32 = bind_user32()
    candidates = toplevel_hwnds(user32, widget_hwnd_value(widget))
    if not candidates:
        return False
    for hwnd in candidates:
        place_topmost(user32, hwnd, enabled)
    rooted = is_topmost_hwnd(user32, candidates[0])
    keep_quiet(widget)
    return rooted if enabled else not rooted


def window_is_topmost(widget) -> bool:
    """读取顶层外壳窗口是否带 WS_EX_TOPMOST。非 Windows 只看 Tk 的 -topmost。"""
    if os.name != "nt":
        try:
            return bool(widget.attributes("-topmost"))
        except Exception:
            return False
    user32 = bind_user32()
    candidates = toplevel_hwnds(user32, widget_hwnd_value(widget))
    if not candidates:
        return False
    return is_topmost_hwnd(user32, candidates[0])


def prepare_quiet_window(user32, hwnd, *, tool: bool = False, taskbar: bool = False) -> int:
    """给已经存在的窗口加上 WS_EX_NOACTIVATE。窗口仍然可见，也不变成点击穿透。"""
    style = exstyle(user32, hwnd) | WS_EX_NOACTIVATE
    if tool:
        style |= WS_EX_TOOLWINDOW
        style &= ~WS_EX_APPWINDOW
    elif taskbar:
        style |= WS_EX_APPWINDOW
        style &= ~WS_EX_TOOLWINDOW
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
    user32.SetWindowPos(hwnd, hwnd, 0, 0, 0, 0, _STYLE_FLAGS)
    return exstyle(user32, hwnd)


def reveal_quiet(user32, hwnd) -> None:
    """显示窗口，但不用会激活前台的 ShowWindow 命令。"""
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)


def mark_quiet_window(widget, *, tool: bool = False, taskbar: bool = False) -> None:
    widget._stinger_quiet = (bool(tool), bool(taskbar))


def _quiet_mark(widget):
    return getattr(widget, "_stinger_quiet", None)


def keep_quiet(widget) -> None:
    """刷新文字或移动之后，重新写上不激活样式。不把焦点送回别的程序。"""
    if os.name != "nt":
        return
    mark = _quiet_mark(widget)
    if not mark:
        return
    user32 = bind_user32()
    handles = toplevel_hwnds(user32, widget_hwnd_value(widget))
    if not handles:
        return
    prepare_quiet_window(user32, handles[0], tool=mark[0], taskbar=mark[1])


def show_without_activating(widget, *, tool: bool = False, taskbar: bool = False) -> bool:
    """显示一个已经建好的可见窗口，不调用 lift、focus 或 grab。"""
    mark_quiet_window(widget, tool=tool, taskbar=taskbar)
    if os.name != "nt":
        try:
            widget.deiconify()
        except Exception:
            return False
        return True
    user32 = bind_user32()
    handles = toplevel_hwnds(user32, widget_hwnd_value(widget))
    if not handles:
        return False
    for hwnd in handles:
        prepare_quiet_window(user32, hwnd, tool=tool, taskbar=taskbar)
        reveal_quiet(user32, hwnd)
    try:
        widget.deiconify()
    except Exception:
        return False
    keep_quiet(widget)
    return True


def position_without_activating(widget, width: int, height: int, x: int, y: int) -> None:
    """移动可见边框。Windows 上用带 SWP_NOACTIVATE 的 SetWindowPos。"""
    widget.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")
    if os.name != "nt":
        return
    user32 = bind_user32()
    handles = toplevel_hwnds(user32, widget_hwnd_value(widget))
    if not handles:
        return
    user32.SetWindowPos(handles[0], handles[0], int(x), int(y), int(width), int(height), _MOVE_FLAGS)
    keep_quiet(widget)


def detach_from_owner(widget) -> bool:
    """设置窗最小化时，答案面板和识别框仍留在桌面上。窗口仍可见。"""
    if os.name != "nt":
        return False
    user32 = bind_user32()
    candidates = toplevel_hwnds(user32, widget_hwnd_value(widget))
    if not candidates:
        return False
    # GWLP_HWNDPARENT. 0 表示没有所有者，不是隐藏，也不是穿透。
    user32.SetWindowLongPtrW(candidates[0], -8, 0)
    return True


def python_too_new() -> str | None:
    if sys.version_info >= (3, 13):
        return (
            "当前 Python 是 3.13 或更新版本。"
            "本程序钉住的 rapidocr-onnxruntime 1.4.4 只声明支持到 3.12。"
            "请安装 64 位 Python 3.12。"
        )
    if sys.version_info < (3, 12):
        return "请使用 64 位 Python 3.12。当前钉住的 numpy 2.5.5 没有更旧版本的 Windows 轮子。"
    return None
