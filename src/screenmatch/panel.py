"""单独的可见答案面板。可拖动、可改大小，刷新时不抢焦点。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from screenmatch.display_state import AnswerBoard
from screenmatch.macui import ANSWER_RED, INK, PLATINUM, WELL, ClassicButton
from screenmatch.present import SIMILARITY_HINT, compact_panel_rows, short_panel_status


class AnswerPanel(tk.Toplevel):
    def __init__(self, master: tk.Misc, font: str, on_top_toggle) -> None:
        super().__init__(master)
        self.withdraw()
        from screenmatch.winfocus import mark_quiet_window

        mark_quiet_window(self, taskbar=True)
        self.title("Stinger")
        self._font = font
        self._expanded = False
        self._on_top_toggle = on_top_toggle
        self.board = AnswerBoard()
        width = 360
        height = 220
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        left = max(screen_width - width - 40, 20)
        top = 48 if screen_height > 500 else 20
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.minsize(260, 120)
        self.resizable(True, True)
        self.configure(bg=PLATINUM)
        self.protocol("WM_DELETE_WINDOW", self._hide_only)

        bar = tk.Frame(self, bg=PLATINUM, padx=6, pady=4)
        bar.pack(fill=tk.X)
        self.more = ClassicButton(bar, text="5条", command=self._toggle_expand, font=(font, 10))
        self.more.pack(side=tk.RIGHT)
        self.top_button = ClassicButton(bar, text="置顶", command=on_top_toggle, font=(font, 10))
        self.top_button.pack(side=tk.RIGHT, padx=(0, 4))

        self.text = tk.Text(
            self,
            wrap="word",
            font=(font, 12),
            bg=WELL,
            fg=INK,
            padx=8,
            pady=4,
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=INK,
            spacing1=1,
            spacing3=1,
            takefocus=0,
        )
        self.text.tag_configure("meta", foreground="#333333", font=(font, 10))
        self.text.tag_configure("badge", foreground=INK, font=(font, 10, "bold"))
        self.text.tag_configure("answer", foreground=ANSWER_RED, font=(font, 16, "bold"))
        self.text.tag_configure("status", foreground="#333333", font=(font, 12))
        self._tip = SIMILARITY_HINT
        self.text.bind("<Enter>", self._show_tip)
        self.text.bind("<Leave>", self._hide_tip)
        self._tip_window = None
        scroll = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.bind("<Key>", self._block_edit)
        self.render()

    def screen_rect(self) -> dict | None:
        if not self.winfo_exists() or not self.winfo_viewable():
            return None
        return {
            "left": int(self.winfo_rootx()),
            "top": int(self.winfo_rooty()),
            "width": max(int(self.winfo_width()), 1),
            "height": max(int(self.winfo_height()), 1),
        }

    def render(self) -> None:
        outcome = self.board.outcome
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if outcome is None:
            status = short_panel_status(self.board.notice)
            if status:
                self.text.insert("end", status + "\n", "status")
        else:
            rows = compact_panel_rows(outcome, self._expanded)
            for index, row in enumerate(rows):
                if index:
                    self.text.insert("end", "\n")
                bank = f"  {row['bank']}" if row.get("bank") else ""
                self.text.insert("end", f"题干匹配度 {row['percent']}%  {row['excerpt']}{bank}", "meta")
                if row["review"]:
                    self.text.insert("end", "  待确认", "badge")
                self.text.insert("end", "\n")
                self.text.insert("end", row["letter_line"] + "\n", "answer")
                for content in row["contents"]:
                    self.text.insert("end", content + "\n", "answer")
        self.text.configure(state="normal")
        extra = outcome is not None and len(outcome.candidates) > 3
        self.more.configure(state="normal" if extra or self._expanded else "disabled")
        self.more.configure(text="3条" if self._expanded else "5条")
        from screenmatch.winfocus import keep_quiet

        keep_quiet(self)

    def _show_tip(self, _event=None) -> None:
        if self._tip_window is not None:
            return
        from screenmatch.winfocus import set_window_topmost, show_without_activating

        tip = tk.Toplevel(self)
        tip.withdraw()
        tip.overrideredirect(True)
        tip.configure(bg=INK)
        label = tk.Label(tip, text=self._tip, bg=PLATINUM, fg=INK, padx=8, pady=4, font=(self._font, 9), bd=1, relief="solid")
        label.pack()
        x = self.winfo_rootx() + 8
        y = self.winfo_rooty() + max(self.winfo_height(), 1) - 8
        tip.geometry(f"+{x}+{y}")
        show_without_activating(tip, tool=True)
        set_window_topmost(tip, True)
        self._tip_window = tip

    def _hide_tip(self, _event=None) -> None:
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        self.render()

    def _hide_only(self) -> None:
        self.withdraw()

    def _block_edit(self, event):
        if (event.state & 0x4) and event.keysym.lower() in {"c", "a", "insert"}:
            return None
        if event.keysym in {
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
        }:
            return None
        return "break"
