"""早期 Macintosh 式控件。灰阶、细黑边、浅浮雕。不是 Apple 官方界面。"""

from __future__ import annotations

import tkinter as tk

PLATINUM = "#DDDDDD"
FACE = "#D4D4D4"
FACE_HOVER = "#ECECEC"
FACE_PRESSED = "#BEBEBE"
INK = "#000000"
WELL = "#FFFFFF"
MUTED = "#555555"
PAUSE_FACE = "#1A1A1A"
PAUSE_HOVER = "#333333"
PAUSE_PRESSED = "#000000"
PAPER = "#F4F4F4"

ANSWER_RED = "#c62828"
ROLES = {
    "plain": {"face": FACE, "hover": FACE_HOVER, "pressed": FACE_PRESSED, "fg": INK, "ring": 1, "border": 2},
    "frame": {"face": FACE, "hover": FACE_HOVER, "pressed": FACE_PRESSED, "fg": INK, "ring": 3, "border": 3},
    "start": {"face": FACE, "hover": FACE_HOVER, "pressed": FACE_PRESSED, "fg": INK, "ring": 2, "border": 3},
    "pause": {"face": PAUSE_FACE, "hover": PAUSE_HOVER, "pressed": PAUSE_PRESSED, "fg": WELL, "ring": 3, "border": 3},
}


class ClassicButton(tk.Button):
    """浮雕按钮。颜色写在控件自己身上，不依赖会忽略背景的原生 ttk。"""

    def __init__(self, master, role: str = "plain", **kwargs) -> None:
        self._role = role if role in ROLES else "plain"
        super().__init__(master, **kwargs)
        self.configure(
            relief="raised",
            highlightcolor=INK,
            cursor="hand2",
            padx=14,
            pady=8,
        )
        self._paint(False)
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")

    def set_role(self, role: str) -> None:
        self._role = role if role in ROLES else "plain"
        self._paint(False)

    def _paint(self, hover: bool) -> None:
        spec = ROLES[self._role]
        disabled = str(self.cget("state")) == "disabled"
        face = spec["face"]
        if hover and not disabled:
            face = spec["hover"]
        self.configure(
            bg=face,
            fg=spec["fg"],
            activebackground=spec["pressed"],
            activeforeground=spec["fg"],
            disabledforeground=MUTED,
            borderwidth=spec["border"],
            highlightthickness=spec["ring"],
            highlightbackground=INK,
        )

    def _enter(self, _event=None) -> None:
        self._paint(True)

    def _leave(self, _event=None) -> None:
        self._paint(False)


class DefaultButton(tk.Frame):
    """开始搜索的双线外框：黑边、窄缝、再一圈黑边。"""

    def __init__(self, master, role: str = "start", **kwargs) -> None:
        super().__init__(master, bg=INK, padx=3, pady=3, highlightthickness=0, bd=0)
        gap = tk.Frame(self, bg=PLATINUM, padx=2, pady=2, highlightthickness=0, bd=0)
        gap.pack(fill=tk.BOTH, expand=True)
        self.button = ClassicButton(gap, role=role, **kwargs)
        self.button.pack(fill=tk.BOTH, expand=True)
