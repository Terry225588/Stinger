"""中文桌面界面。框选松开后立即识别，画面稳定变化后再查一次。"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, ttk

from screenmatch.bank import (
    ALL_BANKS,
    BankCatalog,
    BankFormatError,
    QuestionBank,
    format_batch_report,
    load_bank_cache,
)
from screenmatch.capture import MssGrabber, image_signature, top_band
from screenmatch.display_state import AnswerBoard
from screenmatch.geometry import rectangles_overlap
from screenmatch.match import match_stem_prefix, match_text
from screenmatch.hotkeys import (
    DEFAULT_FRAME,
    DEFAULT_PAUSE,
    parse_accelerator,
    poll_hotkey_ids,
    register_hotkey,
    unregister_hotkey,
)
from screenmatch.macui import INK, PLATINUM, WELL, ClassicButton, DefaultButton
from screenmatch.outline import BorderOverlay, clamp_inner
from screenmatch.ocr_engine import RapidOcrEngine, bundled_model_report
from screenmatch.panel import AnswerPanel
from screenmatch.present import format_import, format_outcome
from screenmatch.template_bank import export_template
from screenmatch.recognition import is_same_recognition, recognition_key
from screenmatch.region_select import select_region
from screenmatch.watch import ScreenWatch
from screenmatch.winfocus import detach_from_owner, set_window_topmost, show_without_activating

def dispatch_watch_event(app, event) -> None:
    """识别结果只改文字。不 lift、不 focus、不 grab，也不为了刷新而 deiconify。"""
    kind = event[0]
    if kind == "status":
        app.status.set(event[1])
    elif kind == "same":
        app.status.set("识别文字没有实质变化，没有重新查询。")
    elif kind == "result":
        text, outcome = event[1], event[2]
        app.board.apply_match(outcome)
        app.panel.render()
        app._show_text(format_outcome(outcome, text), outcome.status)
        app.status.set("识别完成。答案在浮动面板。")
    elif kind == "invalid":
        app._invalidate(event[1])
        app.status.set(event[1])
    elif kind == "overlap":
        app._invalidate(
            "答案面板盖住了识别区域。请把面板拖到区域外面。"
            "这一帧没有识别，以免把面板上的字再读进去。"
        )
        app.status.set("面板与识别区域重叠，已暂停这一帧。")
    elif kind == "error":
        app._invalidate(event[1] + " 上一题答案已作废。")
        app._show_text(event[1] + "\n", "none")
        app.status.set(event[1])


_BANNER_COLOR = {
    "high": "#000000",
    "medium": "#000000",
    "low": "#000000",
    "ambiguous": "#000000",
    "none": "#000000",
}


def _icon_file() -> Path | None:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    roots.append(Path(__file__).resolve().parents[2])
    for root in roots:
        for name in ("stinger-app-icon.jpg", "stinger.ico"):
            candidate = root / "assets" / name
            if candidate.is_file():
                return candidate
    return None


def _legacy_bank_cache() -> Path:
    if os.name == "nt":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "ScreenMatch" / "bank.json"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "screenmatch" / "bank.json"


def resolve_data_dir() -> Path:
    override = os.environ.get("SCREENMATCH_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "Stinger"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "stinger"


class App(tk.Tk):
    def __init__(self, data_dir: Path | None = None) -> None:
        super().__init__()
        self.data_dir = Path(data_dir) if data_dir else resolve_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = BankCatalog()
        self.bank = QuestionBank([])
        self.watch: ScreenWatch = ScreenWatch(stable_s=0.45)
        self.engine = RapidOcrEngine()
        self.events: queue.Queue = queue.Queue()
        self._done_q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._watch_thread: threading.Thread | None = None
        self._region: dict | None = None
        self._selecting = False
        self._was_paused = True
        self._user_paused = True
        self._outline_adjusting = False
        self.outline = None
        self._last_recognition: str | None = None
        self._frame_hotkey = DEFAULT_FRAME
        self._pause_hotkey = DEFAULT_PAUSE
        self._tk_hotkeys: list[str] = []
        self._system_hotkeys: list[tuple[int, int, int]] = []
        self.watch.pause()
        self._font = "TkDefaultFont"
        self.title("Stinger")
        self.geometry("900x640")
        self.minsize(720, 520)
        self.capture_blocked = False
        self._overlap_latched = False
        self.board = AnswerBoard()
        self._build()
        self._load_saved()
        self._apply_hotkeys()
        self._apply_topmost()
        self.after(200, self._detach_panel)
        _root, missing_models = bundled_model_report()
        if missing_models:
            self.status.set("本地 OCR 模型未就绪：" + "；".join(missing_models))
        self.after(120, self._poll)
        self.bind("<Unmap>", self._on_unmap)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.report_callback_exception = self._on_callback_error

    def _apply_icon(self) -> None:
        path = _icon_file()
        if path is None:
            return
        try:
            from PIL import Image, ImageTk

            image = Image.open(path).convert("RGBA")
            self._icon_image = ImageTk.PhotoImage(image.resize((64, 64)))
            self.iconphoto(True, self._icon_image)
            if getattr(self, "panel", None) is not None:
                self.panel.iconphoto(False, self._icon_image)
        except Exception as exc:
            self._log(f"图标未能加载：{exc}")

    def load_bank_file(self, path: str) -> object:
        stored, report = self.catalog.add_file(path)
        self.catalog.use(stored.source_name)
        self.bank = self.catalog.active()
        self.catalog.save(self.data_dir)
        self._last_recognition = None
        self._refresh_bank_label()
        self._invalidate("题库已更换。上一题答案已作废。")
        rejected = [(item.row, item.reason) for item in report.rejected]
        self._show_text(
            format_import(report.valid_count, report.counts(), rejected, replaced=True),
            "high" if report.valid_count else "none",
        )
        self.status.set(f"已导入「{stored.source_name}」{report.valid_count} 题，跳过 {len(report.rejected)} 行")
        return report

    def query_text(self, text: str):
        outcome = match_text(self.bank, text)
        self.board.apply_match(outcome)
        self.panel.render()
        self._show_text(format_outcome(outcome, text), outcome.status)
        return outcome

    def _build(self) -> None:
        self._font = _pick_font(self)
        self.configure(bg=PLATINUM)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=PLATINUM)
        style.configure("TLabel", background=PLATINUM, foreground=INK, font=(self._font, 11))
        style.configure("Header.TLabel", background=PLATINUM, foreground=INK, font=(self._font, 18, "bold"))
        style.configure("Hint.TLabel", background=PLATINUM, foreground="#222222", font=(self._font, 9))
        style.configure("Status.TLabel", background="#C8C8C8", foreground=INK, font=(self._font, 10))
        style.configure("TCheckbutton", background=PLATINUM, foreground=INK, font=(self._font, 10))
        style.configure(
            "TEntry",
            fieldbackground=WELL,
            foreground=INK,
            bordercolor=INK,
            lightcolor=INK,
            darkcolor=INK,
        )
        style.configure(
            "TCombobox",
            fieldbackground=WELL,
            background=PLATINUM,
            foreground=INK,
            bordercolor=INK,
            arrowcolor=INK,
        )

        outer = ttk.Frame(self, padding=(10, 8))
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, minsize=248, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(2, weight=1)

        title = tk.Frame(outer, bg=PLATINUM)
        title.grid(row=0, column=0, columnspan=2, sticky="w")
        self._place_title_mark(title)
        tk.Label(title, text="Stinger", bg=PLATINUM, fg=INK, font=(self._font, 18, "bold")).pack(side=tk.LEFT, padx=(6, 0))
        actions = ttk.Frame(outer)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.frame_ring = DefaultButton(
            actions, role="frame", text="框选", command=self._begin_select, font=(self._font, 16, "bold")
        )
        self.frame_ring.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=2)
        self.frame_btn = self.frame_ring.button
        self.start_ring = DefaultButton(
            actions, role="start", text="开始搜索", command=self._toggle_pause, font=(self._font, 16, "bold")
        )
        self.start_ring.grid(row=0, column=1, sticky="ew", padx=(8, 0), ipady=2)
        self.pause_btn = self.start_ring.button
        self.region_label = ttk.Label(actions, text="区域：还没有框选", style="Hint.TLabel")
        self.region_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        left = ttk.Frame(outer)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        scroller, side = self._make_side_scroller(left)
        scroller.grid(row=0, column=0, sticky="nsew")
        self.top_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            side,
            text="答案面板置顶（不主动抢焦点）",
            variable=self.top_var,
            command=self._apply_topmost,
        ).pack(anchor="w", pady=(2, 4))

        self.bank_label = ttk.Label(side, text="题库：还没有导入", wraplength=230, justify=tk.LEFT)
        self.bank_label.pack(anchor="w", pady=(2, 2))
        self.bank_mode = tk.StringVar(value=ALL_BANKS)
        self.bank_picker = ttk.Combobox(side, textvariable=self.bank_mode, state="readonly", width=24)
        self.bank_picker.pack(fill=tk.X, pady=1)
        self.bank_picker.bind("<<ComboboxSelected>>", self._switch_bank)
        ClassicButton(side, text="导入题库", command=self._import_bank, font=(self._font, 11)).pack(fill=tk.X, pady=1)
        ClassicButton(side, text="导出模板", command=self._export_template, font=(self._font, 11)).pack(fill=tk.X, pady=1)
        ttk.Label(
            side,
            text="导入题库可选一个或多个 Excel。多个文件会按文件名分别入库。表头要有题型、题目、A 到 F 和答案。",
            style="Hint.TLabel",
            wraplength=230,
        ).pack(anchor="w", pady=(2, 6))

        ttk.Label(side, text="快捷键。窗口内有效；Windows 另登记热键，不用键盘钩子。", style="Hint.TLabel", wraplength=230).pack(
            anchor="w", pady=(2, 2)
        )
        self.frame_var = tk.StringVar(value=DEFAULT_FRAME)
        self.pause_var = tk.StringVar(value=DEFAULT_PAUSE)
        ttk.Label(side, text="框选", style="TLabel").pack(anchor="w")
        ttk.Entry(side, textvariable=self.frame_var, font=(self._font, 10)).pack(fill=tk.X, pady=1)
        ttk.Label(side, text="暂停或继续", style="TLabel").pack(anchor="w")
        ttk.Entry(side, textvariable=self.pause_var, font=(self._font, 10)).pack(fill=tk.X, pady=1)
        ClassicButton(side, text="应用快捷键", command=self._apply_hotkeys, font=(self._font, 11)).pack(fill=tk.X, pady=1)
        ClassicButton(side, text="最小化设置窗", command=self.iconify, font=(self._font, 11)).pack(fill=tk.X, pady=1)

        ttk.Label(side, text="手动粘贴识别文本", style="TLabel").pack(anchor="w", pady=(6, 2))
        self.paste = tk.Text(
            side,
            height=4,
            width=24,
            wrap="word",
            font=(self._font, 10),
            bg=WELL,
            fg=INK,
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=INK,
        )
        self.paste.pack(fill=tk.X)
        ClassicButton(side, text="用这段文字查询", command=self._query_paste, font=(self._font, 11)).pack(fill=tk.X, pady=2)
        ttk.Label(
            side,
            text="第一次框选会打开普通遮罩并拿走焦点。松开后不把设置窗拉回前台，也不把焦点送回网页。",
            style="Hint.TLabel",
            wraplength=230,
        ).pack(anchor="w", pady=(4, 2))
        self.path_label = ttk.Label(side, text=f"题库副本：{self.data_dir}", style="Hint.TLabel", wraplength=230)
        self.path_label.pack(anchor="w", pady=(0, 4))

        right = ttk.Frame(outer)
        right.grid(row=2, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.result = tk.Text(
            right,
            wrap="word",
            font=(self._font, 12),
            bg=WELL,
            fg=INK,
            padx=12,
            pady=10,
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=INK,
        )
        scroll = ttk.Scrollbar(right, command=self.result.yview)
        self.result.configure(yscrollcommand=scroll.set)
        self.result.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.result.bind("<Key>", self._block_edit)
        self._show_text(
            "先点「框选」拖出题目区域。松开后会开始搜索。\n"
            "正在搜索时按钮是「暂停搜索」。停下来之后按钮变回「开始搜索」。\n",
            "none",
        )

        self.status = tk.StringVar(value="就绪")
        ttk.Label(outer, textvariable=self.status, style="Status.TLabel").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        self.panel = AnswerPanel(self, self._font, self._toggle_top_from_panel)
        self.panel.board = self.board
        self.panel.render()
        self._apply_icon()
        show_without_activating(self.panel, taskbar=True)
        self.bind("<Configure>", self._fit_header_wrap, add="+")

    def _make_side_scroller(self, parent: ttk.Frame) -> tuple[ttk.Frame, ttk.Frame]:
        """侧栏多余项放进滚动区。滚轮只滚动这块，不调用 focus 或置顶。"""
        holder = ttk.Frame(parent)
        canvas = tk.Canvas(holder, highlightthickness=1, highlightbackground=INK, bg=PLATINUM, width=236, height=120, bd=0)
        bar = ttk.Scrollbar(holder, command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        inner = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _fit_inner(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, 0, 0))

        def _fit_width(event) -> None:
            canvas.itemconfigure(window_id, width=max(event.width, 1))

        def _wheel(event):
            if getattr(event, "num", None) == 4:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(3, "units")
            else:
                steps = int(-getattr(event, "delta", 0) / 120) or (-1 if getattr(event, "delta", 0) > 0 else 1)
                canvas.yview_scroll(steps, "units")
            return "break"

        def _pointer_inside() -> bool:
            try:
                x, y = holder.winfo_pointerxy()
                left, top = holder.winfo_rootx(), holder.winfo_rooty()
                return left <= x < left + holder.winfo_width() and top <= y < top + holder.winfo_height()
            except tk.TclError:
                return False

        def _arm(_event=None) -> None:
            canvas.bind_all("<MouseWheel>", _wheel)
            canvas.bind_all("<Button-4>", _wheel)
            canvas.bind_all("<Button-5>", _wheel)

        def _disarm(_event=None) -> None:
            if _pointer_inside():
                return
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        inner.bind("<Configure>", _fit_inner)
        canvas.bind("<Configure>", _fit_width)
        holder.bind("<Enter>", _arm)
        holder.bind("<Leave>", _disarm)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.side_canvas = canvas
        return holder, inner

    def _fit_header_wrap(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        width = max(int(self.winfo_width()) - 24, 280)
        if hasattr(self, "_header_hint"):
            self._header_hint.configure(wraplength=width)

    def _import_bank(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title="选择题库，可以多选",
            filetypes=[("Excel 工作簿", "*.xlsx")],
        )
        self.import_selected_files([path for path in paths if path])

    def import_selected_files(self, paths) -> str | None:
        files = [path for path in paths if path]
        if not files:
            return None
        if len(files) == 1:
            try:
                self.load_bank_file(files[0])
            except BankFormatError as exc:
                self._show_text(str(exc) + "\n", "none")
                self.status.set(str(exc))
            return None
        return self.import_bank_paths(files)

    def _export_template(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="导出题库模板",
            defaultextension=".xlsx",
            initialfile="Stinger题库模板.xlsx",
            filetypes=[("Excel 工作簿", "*.xlsx")],
        )
        if not path:
            self.status.set("已取消导出模板")
            return
        self.write_exported_template(path)

    def write_exported_template(self, path: str) -> str:
        try:
            saved = export_template(path)
        except OSError as exc:
            message = f"导出模板失败：{exc}"
            self._show_text(message + "\n", "none")
            self.status.set(message)
            raise
        message = f"已导出模板：{saved}"
        self.status.set(message)
        self._show_text(
            "模板已保存。\n"
            "表头：题型、题目、A、B、C、D、E、F、答案、难度、试题依据、试题解析、保命题。\n"
            "单选题答案填一个字母，例如 A。多选题填 A,B,C。判断题选项写「正确」和「错误」，答案填「正确」或「错误」。\n"
            "文件里的三行都标了【示例】，请换成自己的题目后再导入。\n"
            f"文件：{saved}\n",
            "high",
        )
        return str(saved)

    def import_bank_paths(self, paths) -> str:
        files = [Path(path) for path in paths]
        if not files:
            report = format_batch_report([])
            self._show_text(report, "none")
            self.status.set("没有选到 Excel 文件")
            return report
        results = self.catalog.add_files(files)
        if self.catalog.mode not in self.catalog.entries and self.catalog.mode != ALL_BANKS:
            self.catalog.use(ALL_BANKS)
        self.bank = self.catalog.active()
        try:
            self.catalog.save(self.data_dir)
        except OSError as exc:
            self._log(f"保存题库目录失败：{exc}")
        self._last_recognition = None
        self._refresh_bank_label()
        self._invalidate("题库已更换。上一题答案已作废。")
        report = format_batch_report(results)
        failed = sum(1 for _name, item, _error in results if item is None)
        self._show_text(report, "none" if failed else "high")
        self.status.set(f"已导入 {len(files)} 个文件，失败 {failed} 个")
        return report

    def _query_paste(self) -> None:
        text = self.paste.get("1.0", "end").strip()
        if not text:
            self.status.set("请先在左侧粘贴文字")
            return
        self.query_text(text)
        self.status.set("已用粘贴文本在本地题库中查找")

    def _begin_select(self) -> None:
        if self._selecting:
            return
        self._was_paused = self.watch.controller.is_paused()
        self.watch.pause()
        self._selecting = True
        self._set_search_button()
        self._invalidate("正在重新框选。上一题答案已作废。")
        self.status.set("请拖出区域。松开鼠标后立即识别，不需要再点一次。")
        self.after(30, self._open_overlay)

    def _open_overlay(self) -> None:
        try:
            region = select_region(self)
        except Exception as exc:
            self._selecting = False
            self._set_search_button()
            self.status.set(f"框选失败：{exc}")
            self._log(traceback.format_exc())
            return
        self.after(200, lambda: self._after_select(region))

    def _after_select(self, region: dict | None) -> None:
        self._selecting = False
        if not region:
            if self._region is not None and not self._was_paused:
                self.watch.resume()
                self._set_search_button()
                self.status.set("已取消框选，继续搜索原来的区域")
            else:
                self._set_search_button()
                self.status.set("已取消框选" if self._region else "还没有框选区域")
            return
        self._user_paused = False
        self._show_outline(region, paused=False)
        self._save_config()
        self._refresh_region_label()
        self.watch.arm_immediate()
        self.watch.resume()
        self._set_search_button()
        self._ensure_watch()
        self.status.set("识别框留在屏幕上。边框在内容外面，中间的点击会落到网页。松开后立即识别。")

    def _toggle_pause(self) -> None:
        if self._region is None:
            self.status.set("请先框选一块区域")
            return
        if self._user_paused:
            self._user_paused = False
            self.watch.arm_immediate()
            self.watch.resume()
            self._set_search_button()
            if self.outline is not None:
                self.outline.set_paused(False)
            self._ensure_watch()
            self.status.set("已开始搜索。文字稳定变化后会自动再查。")
        else:
            self._user_paused = True
            self.watch.pause()
            self._set_search_button()
            if self.outline is not None:
                self.outline.set_paused(True)
            self._invalidate("已暂停。上一题答案已作废，不再当作当前题。")
            self.status.set("已暂停。识别框仍留在屏幕上，边框改成暂停颜色。")

    def _place_title_mark(self, parent: tk.Frame) -> None:
        path = _icon_file()
        if path is None:
            return
        try:
            from PIL import Image, ImageTk

            image = Image.open(path).convert("RGBA").resize((22, 22), Image.Resampling.NEAREST)
            self._title_mark = ImageTk.PhotoImage(image)
            tk.Label(parent, image=self._title_mark, bg=PLATINUM, bd=0).pack(side=tk.LEFT)
        except Exception as exc:
            self._log(f"标题小图未能加载：{exc}")

    def _set_search_button(self) -> None:
        running = (not self._user_paused) and not self._selecting
        self.pause_btn.configure(text="暂停搜索" if running else "开始搜索")
        self.pause_btn.set_role("pause" if running else "start")

    def _ensure_watch(self) -> None:
        if self._watch_thread and self._watch_thread.is_alive():
            return
        self._stop.clear()
        self._watch_thread = threading.Thread(target=self._watch_loop, name="screen-watch", daemon=True)
        self._watch_thread.start()

    def _watch_loop(self) -> None:
        grabber = None
        try:
            while not self._stop.is_set():
                try:
                    self._drain_finished()
                    region = self._region
                    if (
                        region is None
                        or self.watch.controller.is_paused()
                        or self._selecting
                        or self._outline_adjusting
                    ):
                        self._stop.wait(0.2)
                        continue
                    if self.capture_blocked:
                        if not self._overlap_latched:
                            self._overlap_latched = True
                            self.events.put(("overlap",))
                        self._stop.wait(0.2)
                        continue
                    if grabber is None:
                        grabber = MssGrabber()
                    frame = grabber.grab(region)
                    signature = image_signature(frame)
                    payload = self.watch.observe(signature, frame, time.monotonic())
                    if payload is not None:
                        self._start_job(payload)
                except Exception as exc:
                    self.events.put(("error", f"截屏失败：{exc}"))
                    self._log(traceback.format_exc())
                    self._stop.wait(0.6)
                    continue
                self._stop.wait(0.2)
        finally:
            if grabber is not None:
                grabber.close()

    def _drain_finished(self) -> None:
        while True:
            try:
                self._done_q.get_nowait()
            except queue.Empty:
                return
            follow = self.watch.complete()
            if follow is not None:
                self._start_job(follow)
                return

    def _start_job(self, frame) -> None:
        self.events.put(("status", "正在识别…"))
        threading.Thread(target=self._run_job, args=(frame,), daemon=True).start()

    def _run_job(self, frame) -> None:
        try:
            bank = self.bank
            if not bank.questions:
                self.events.put(("error", "请先导入题库（Excel）。这一帧没有查询。"))
                return
            text_top = ""
            try:
                text_top = self.engine.recognize(top_band(frame))
            except Exception:
                text_top = ""
            early = match_stem_prefix(bank, text_top or "")
            if early is not None and not early.needs_more:
                self._finish_recognition(frame, text_top or "", early)
                return
            text = self.engine.recognize(frame)
            if not (text or "").strip():
                self._last_recognition = None
                self.events.put(("invalid", "这一帧没有识别到文字。上一题答案已作废。"))
                return
            if is_same_recognition(self._last_recognition, text):
                self.events.put(("same",))
                return
            outcome = match_text(bank, text)
            self._finish_recognition(frame, text, outcome)
        except Exception as exc:
            self.events.put(("error", f"识别失败：{exc}"))
            self._log(traceback.format_exc())
        finally:
            self._done_q.put(True)

    def _finish_recognition(self, frame, text: str, outcome) -> None:
        key = recognition_key(text)
        if is_same_recognition(self._last_recognition, text):
            self.events.put(("same",))
            return
        self._last_recognition = key
        self.events.put(("result", text, outcome))

    def _poll(self) -> None:
        self._poll_system_hotkeys()
        self._update_overlap()
        try:
            while True:
                dispatch_watch_event(self, self.events.get_nowait())
        except queue.Empty:
            pass
        if not self._stop.is_set():
            self.after(120, self._poll)

    def _update_overlap(self) -> None:
        rect = self.panel.screen_rect() if hasattr(self, "panel") else None
        blocked = bool(self._region and rect and rectangles_overlap(self._region, rect))
        self.capture_blocked = blocked
        if not blocked:
            self._overlap_latched = False

    def _invalidate(self, reason: str) -> None:
        if self.board.notice == reason and self.board.outcome is None and not self.board.show_current:
            return
        self.board.invalidate(reason)
        if hasattr(self, "panel"):
            self.panel.render()

    def _toggle_top_from_panel(self) -> None:
        self.top_var.set(not self.top_var.get())
        self._apply_topmost()

    def _apply_topmost(self) -> None:
        if not hasattr(self, "panel"):
            return
        enabled = bool(self.top_var.get())
        self._save_config()
        set_window_topmost(self.panel, enabled)
        self.panel.top_button.configure(text="取消置顶" if enabled else "面板置顶")

    def _detach_panel(self) -> None:
        if not hasattr(self, "panel"):
            return
        detach_from_owner(self.panel)
        set_window_topmost(self.panel, bool(self.top_var.get()))

    def _on_unmap(self, event) -> None:
        if event.widget is not self:
            return
        self.after(80, self._keep_panel_visible)

    def _keep_panel_visible(self) -> None:
        if not hasattr(self, "panel") or not self.panel.winfo_exists():
            return
        if str(self.state()) != "iconic":
            return
        show_without_activating(self.panel, taskbar=True)
        set_window_topmost(self.panel, bool(self.top_var.get()))

    def _show_text(self, content: str, status: str) -> None:
        widget = self.result
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.tag_add("banner", "1.0", "1.end")
        widget.tag_configure(
            "banner",
            font=(self._font, 15, "bold"),
            foreground=_BANNER_COLOR.get(status, "#1c1915"),
        )
        widget.configure(state="normal")
        widget.see("1.0")

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

    def _refresh_bank_label(self) -> None:
        names = self.catalog.names()
        if hasattr(self, "bank_picker"):
            self.bank_picker.configure(values=[ALL_BANKS, *names] if names else [ALL_BANKS])
            self.bank_mode.set(self.catalog.mode if self.catalog.mode in names or self.catalog.mode == ALL_BANKS else ALL_BANKS)
        if not self.bank.questions:
            self.bank_label.configure(text="题库：还没有导入")
            return
        counts = self.bank.counts()
        groups = len(self.bank.duplicate_groups)
        scope = "全部题库" if self.catalog.mode == ALL_BANKS else self.catalog.mode
        text = (
            f"当前：{scope}\n"
            f"{len(self.bank.questions)} 题（单选 {counts['single']}，多选 {counts['multi']}，判断 {counts['judgment']}）"
        )
        if groups:
            text += f"\n有 {groups} 组题干相同但题目不同。只看题干时不会给确定答案。"
        self.bank_label.configure(text=text)

    def _switch_bank(self, _event=None) -> None:
        self.catalog.use(self.bank_mode.get())
        self.bank = self.catalog.active()
        self._last_recognition = None
        try:
            self.catalog.save(self.data_dir)
        except OSError as exc:
            self._log(f"保存题库目录失败：{exc}")
        self._invalidate("已切换题库。上一题答案已作废。")
        self._refresh_bank_label()

    def _refresh_region_label(self) -> None:
        if not self._region:
            self.region_label.configure(text="区域：还没有框选")
            return
        region = self._region
        self.region_label.configure(
            text=f"区域：左 {region['left']}，上 {region['top']}，{region['width']} × {region['height']}"
        )

    def _load_saved(self) -> None:
        self.catalog = BankCatalog.load(self.data_dir)
        if not self.catalog.entries:
            for cache in (self.data_dir / "bank.json", _legacy_bank_cache()):
                if not cache.is_file():
                    continue
                try:
                    legacy = load_bank_cache(cache)
                    name = legacy.source_name or "已导入题库"
                    from dataclasses import replace

                    tagged = [replace(question, bank_name=name) for question in legacy.questions]
                    self.catalog.entries[name] = QuestionBank(tagged, name)
                    break
                except (OSError, ValueError):
                    continue
        self.bank = self.catalog.active()
        self._refresh_bank_label()
        config_path = self.data_dir / "config.json"
        if not config_path.is_file():
            return
        try:
            import json

            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        region = config.get("region")
        if isinstance(region, dict) and {"top", "left", "width", "height"} <= set(region):
            self._region = {key: int(region[key]) for key in ("top", "left", "width", "height")}
            self._user_paused = True
            self._show_outline(self._region, paused=True)
            self._refresh_region_label()
            self.status.set("已恢复上次的识别框。点「开始搜索」后才开始截屏。")
        if "topmost" in config:
            self.top_var.set(bool(config["topmost"]))
        if config.get("frame_hotkey"):
            self.frame_var.set(str(config["frame_hotkey"]))
        if config.get("pause_hotkey"):
            self.pause_var.set(str(config["pause_hotkey"]))

    def _save_config(self) -> None:
        import json

        payload = {
            "region": self._region,
            "topmost": bool(self.top_var.get()),
            "frame_hotkey": self.frame_var.get() if hasattr(self, "frame_var") else self._frame_hotkey,
            "pause_hotkey": self.pause_var.get() if hasattr(self, "pause_var") else self._pause_hotkey,
        }
        try:
            (self.data_dir / "config.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            self._log(f"保存配置失败：{exc}")

    def _log(self, text: str) -> None:
        try:
            with (self.data_dir / "error.log").open("a", encoding="utf-8") as handle:
                handle.write(text.rstrip() + "\n")
        except OSError:
            return

    def _on_callback_error(self, exc, val, tb) -> None:
        self._log("".join(traceback.format_exception(exc, val, tb)))
        self.status.set(f"界面出错：{val}")

    def _screen_bounds(self) -> dict:
        return {
            "left": 0,
            "top": 0,
            "width": int(self.winfo_screenwidth()),
            "height": int(self.winfo_screenheight()),
        }

    def _show_outline(self, inner: dict, paused: bool) -> None:
        screen = self._screen_bounds()
        fitted = clamp_inner(inner, screen)
        self._region = fitted
        self._last_recognition = None
        if self.outline is None or not self.outline.alive:
            self.outline = BorderOverlay(
                self,
                fitted,
                screen,
                on_adjust_start=self._outline_start,
                on_adjust_end=self._outline_end,
                paused=paused,
            )
        else:
            self.outline.screen = screen
            self.outline.session.screen = screen
            self.outline.set_inner(fitted)
            self.outline.set_paused(paused)

    def _outline_start(self) -> None:
        self._adjust_was_paused = self._user_paused
        self._outline_adjusting = True
        self.watch.pause()
        if self.outline is not None:
            self.outline.set_paused(True)
        self._invalidate("正在移动识别框。上一题答案已作废。")
        self.status.set("正在移动识别框，这段时间不截屏。")

    def _outline_end(self, inner: dict) -> None:
        self._region = clamp_inner(inner, self._screen_bounds())
        self._outline_adjusting = False
        self._save_config()
        self._refresh_region_label()
        if self.outline is not None:
            self.outline.set_paused(self._adjust_was_paused)
        if self._adjust_was_paused:
            self.status.set("识别框已放下。监听仍暂停。")
            return
        self.watch.resume()
        self._ensure_watch()
        self.status.set("识别框已放下。画面稳定后会自动再查，不用再点一次。")

    def _apply_hotkeys(self) -> None:
        frame = parse_accelerator(self.frame_var.get())
        pause = parse_accelerator(self.pause_var.get())
        if frame is None or pause is None:
            self.status.set("快捷键无法识别。示例：Ctrl+Alt+F 和 Ctrl+Alt+P")
            return
        for sequence in self._tk_hotkeys:
            self.unbind_all(sequence)
        self._tk_hotkeys = []
        self.bind_all(frame[0], self._hot_frame)
        self.bind_all(pause[0], self._hot_pause)
        self._tk_hotkeys = [frame[0], pause[0]]
        self._frame_hotkey = self.frame_var.get().strip()
        self._pause_hotkey = self.pause_var.get().strip()
        self._save_config()
        self._register_system_hotkeys([(1, frame[1], frame[2]), (2, pause[1], pause[2])])
        if "识别框" not in self.status.get():
            self.status.set(f"快捷键：框选 {self._frame_hotkey}，暂停 {self._pause_hotkey}")

    def _hot_frame(self, _event=None):
        if not self._selecting:
            self._begin_select()
        return "break"

    def _hot_pause(self, _event=None):
        self._toggle_pause()
        return "break"

    def _register_system_hotkeys(self, specs: list[tuple[int, int, int]]) -> None:
        self._clear_system_hotkeys()
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            from screenmatch.winfocus import bind_user32, toplevel_hwnds, widget_hwnd_value

            user32 = bind_user32()
            user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            user32.RegisterHotKey.restype = wintypes.BOOL
            user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.UnregisterHotKey.restype = wintypes.BOOL
            handles = toplevel_hwnds(user32, widget_hwnd_value(self))
            if not handles:
                return
            hwnd = handles[0]
            self._hotkey_hwnd = hwnd
            for hotkey_id, mods, vk in specs:
                if register_hotkey(user32, hwnd, hotkey_id, mods, vk):
                    self._system_hotkeys.append((hotkey_id, mods, vk))
            if len(self._system_hotkeys) < len(specs):
                self.status.set("有的系统热键没登记上。本程序窗口里的快捷键仍然可用。")
        except Exception as exc:
            self._log(f"登记热键失败：{exc}")

    def _clear_system_hotkeys(self) -> None:
        if os.name != "nt" or not self._system_hotkeys:
            self._system_hotkeys = []
            return
        try:
            from screenmatch.winfocus import bind_user32

            user32 = bind_user32()
            hwnd = getattr(self, "_hotkey_hwnd", None)
            if hwnd is not None:
                for hotkey_id, _mods, _vk in self._system_hotkeys:
                    unregister_hotkey(user32, hwnd, hotkey_id)
        except Exception as exc:
            self._log(f"取消热键失败：{exc}")
        self._system_hotkeys = []

    def _poll_system_hotkeys(self) -> None:
        if os.name != "nt" or not self._system_hotkeys:
            return
        try:
            import ctypes
            from ctypes import wintypes

            from screenmatch.winfocus import bind_user32

            user32 = bind_user32()
            if not hasattr(user32, "_stinger_msg"):
                class MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", wintypes.HWND),
                        ("message", wintypes.UINT),
                        ("wParam", wintypes.WPARAM),
                        ("lParam", wintypes.LPARAM),
                        ("time", wintypes.DWORD),
                        ("pt_x", ctypes.c_long),
                        ("pt_y", ctypes.c_long),
                    ]

                user32._stinger_msg = MSG
                user32.MSG = MSG
                user32.PeekMessageW.argtypes = [
                    ctypes.POINTER(MSG),
                    wintypes.HWND,
                    wintypes.UINT,
                    wintypes.UINT,
                    wintypes.UINT,
                ]
                user32.PeekMessageW.restype = wintypes.BOOL
            hwnd = getattr(self, "_hotkey_hwnd", None)
            if hwnd is None:
                return
            for hotkey_id in poll_hotkey_ids(user32, hwnd):
                if hotkey_id == 1:
                    self._hot_frame()
                elif hotkey_id == 2:
                    self._hot_pause()
        except Exception as exc:
            self._log(f"读取热键失败：{exc}")

    def _on_close(self) -> None:
        self._stop.set()
        self._clear_system_hotkeys()
        self._save_config()
        if self.outline is not None:
            self.outline.destroy()
            self.outline = None
        self.destroy()


def _pick_font(root: tk.Misc) -> str:
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        return "TkDefaultFont"
    for name in (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "微软雅黑",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "Droid Sans Fallback",
    ):
        if name in families:
            return name
    return "TkDefaultFont"


def main() -> None:
    from screenmatch.winfocus import enable_dpi_awareness, python_too_new

    enable_dpi_awareness()
    note = python_too_new()
    app = App()
    if note:
        app.status.set(note)
        app._show_text(note + "\n", "none")
    app.mainloop()
