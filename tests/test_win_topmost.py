"""核对置顶接口是否导出，并在 Windows 上读取真正的 WS_EX_TOPMOST。

模块级不跳过：Linux 也要能导入 window_is_topmost，避免名字写错却被整文件跳过。
真正开关样式位的用例只在 Windows 上跑。不打开网页，也不做点击穿透。
"""

from __future__ import annotations

import os

import pytest

from screenmatch.winfocus import set_window_topmost, window_is_topmost


def test_winfocus_exports_topmost_helpers():
    import screenmatch.winfocus as winfocus

    assert callable(winfocus.window_is_topmost)
    assert callable(winfocus.set_window_topmost)
    assert callable(winfocus.place_topmost)
    assert callable(winfocus.last_topmost_error)
    assert winfocus.last_topmost_error() == 0
    assert window_is_topmost is winfocus.window_is_topmost
    assert set_window_topmost is winfocus.set_window_topmost


@pytest.mark.skipif(os.name != "nt", reason="只在 Windows 上核对 WS_EX_TOPMOST")
def test_real_toplevel_topmost_bit_toggles():
    import tkinter as tk

    root = tk.Tk()
    child = None
    try:
        root.geometry("240x160+40+40")
        root.update_idletasks()
        root.deiconify()
        root.update()
        assert set_window_topmost(root, True) is True, "置顶失败，Win32 错误码见 last_topmost_error"
        assert window_is_topmost(root) is True
        assert set_window_topmost(root, False) is True
        assert window_is_topmost(root) is False
        child = tk.Toplevel(root)
        child.geometry("200x120+90+90")
        child.update()
        assert set_window_topmost(child, True) is True
        assert window_is_topmost(child) is True
        assert set_window_topmost(child, False) is True
        assert window_is_topmost(child) is False
    finally:
        if child is not None:
            child.destroy()
        root.destroy()
