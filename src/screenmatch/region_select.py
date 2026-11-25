"""全屏拖出一块矩形。松开鼠标就结束，不再要求第二次点击。

框选这一交互参考了 Lihvarya/ibosOCR（Apache-2.0）。这里没有沿用它的脚本：
松开后立即识别，也不注册需要管理员权限的全局热键。

这个遮罩是普通的顶层窗口，会按系统的正常规则拿走焦点。
"""

from __future__ import annotations

import tkinter as tk


def select_region(master: tk.Misc) -> dict | None:
    top = tk.Toplevel(master)
    top.withdraw()
    top.title("框选识别区域")
    top.configure(bg="#202020")
    top.attributes("-topmost", True)
    try:
        top.attributes("-alpha", 0.35)
    except tk.TclError:
        pass
    try:
        top.attributes("-fullscreen", True)
    except tk.TclError:
        pass
    width = master.winfo_screenwidth()
    height = master.winfo_screenheight()
    top.geometry(f"{width}x{height}+0+0")
    top.overrideredirect(True)

    canvas = tk.Canvas(top, cursor="cross", bg="#202020", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    canvas.create_text(
        width // 2,
        48,
        text="按住左键拖出题目区域，松开后立即识别。按 Esc 取消。\n"
        "这是普通遮罩，会暂时拿走焦点。程序不会把焦点送回网页，也不会隐藏窗口。",
        fill="#f4f1ea",
        font=("TkDefaultFont", 14),
        justify=tk.CENTER,
    )

    selected: dict[str, dict] = {}
    start: dict[str, int] = {}
    rect: dict[str, int | None] = {"id": None}

    def on_down(event):
        start["x"], start["y"] = event.x, event.y
        if rect["id"] is not None:
            canvas.delete(rect["id"])
            rect["id"] = None

    def on_drag(event):
        if "x" not in start:
            return
        if rect["id"] is not None:
            canvas.delete(rect["id"])
        rect["id"] = canvas.create_rectangle(
            start["x"], start["y"], event.x, event.y, outline="#d84a3a", width=3
        )

    def on_up(event):
        if "x" not in start:
            _close()
            return
        x1, y1 = min(start["x"], event.x), min(start["y"], event.y)
        x2, y2 = max(start["x"], event.x), max(start["y"], event.y)
        if x2 - x1 >= 20 and y2 - y1 >= 20:
            top.update_idletasks()
            selected["region"] = {
                "left": int(top.winfo_rootx() + x1),
                "top": int(top.winfo_rooty() + y1),
                "width": int(x2 - x1),
                "height": int(y2 - y1),
            }
        _close()

    def on_cancel(_event=None):
        selected.clear()
        _close()

    def _close():
        try:
            top.grab_release()
        except tk.TclError:
            pass
        if top.winfo_exists():
            top.destroy()

    canvas.bind("<ButtonPress-1>", on_down)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_up)
    top.bind("<Escape>", on_cancel)
    canvas.bind("<ButtonPress-3>", on_cancel)
    top.update_idletasks()
    try:
        from screenmatch.winfocus import detach_from_owner

        detach_from_owner(top)
    except Exception:
        pass
    top.deiconify()
    top.focus_force()
    try:
        top.grab_set()
    except tk.TclError:
        pass
    master.wait_window(top)
    return selected.get("region")
