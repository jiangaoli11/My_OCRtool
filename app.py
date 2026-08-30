from __future__ import annotations

import ctypes
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageTk
import pystray

from autostart import is_autostart_enabled, set_autostart
from image_tools import copy_image_to_clipboard, save_image_dialog
from ocr_engine import available_languages, recognize_image
from screenshot_widgets import ImageEditor, PinWindow
from settings_dialog import SettingsDialog
from settings_store import AppSettings, SettingsStore


APP_NAME = "截图 OCR"
APP_VERSION = "2.1.0"
_SINGLE_INSTANCE_HANDLE = None


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def enable_high_dpi() -> None:
    """让多显示器截图坐标与 Tk 坐标保持一致。"""

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def acquire_single_instance() -> bool:
    global _SINGLE_INSTANCE_HANDLE
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _SINGLE_INSTANCE_HANDLE = kernel32.CreateMutexW(
        None,
        False,
        "Local\\ScreenshotOCR_6A2E8A4D",
    )
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            None,
            "截图 OCR 已经在运行，请检查主窗口或系统托盘。",
            APP_NAME,
            0x40,
        )
        return False
    return bool(_SINGLE_INSTANCE_HANDLE)


def run_packaged_self_test(output_path: Path) -> int:
    """供构建流程验证打包后的 WinRT OCR；正常用户无需调用。"""

    try:
        languages = available_languages()
        if not languages:
            raise RuntimeError("Windows 没有安装 OCR 语言包")

        image = Image.new("RGB", (1000, 250), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 78)
        draw.text((45, 65), "截图 OCR 测试 2026", fill="black", font=font)
        language = next(
            (item.tag for item in languages if item.tag.lower().startswith("zh-hans")),
            None,
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(recognize_image, image, language, False).result(timeout=30)
        if not result.strip() or "2026" not in result.replace(" ", ""):
            raise RuntimeError(f"OCR 自检结果异常：{result!r}")
        output_path.write_text(
            "OK\n" + ",".join(item.tag for item in languages) + "\n" + result,
            encoding="utf-8",
        )
        return 0
    except Exception:
        output_path.write_text("FAILED\n" + traceback.format_exc(), encoding="utf-8")
        return 1


class SelectionOverlay:
    MASK_COLOR = "#050b12"
    ACCENT = "#22c55e"

    def __init__(
        self,
        root: tk.Tk,
        screenshot: Image.Image,
        origin_x: int,
        origin_y: int,
        on_selected,
        on_cancelled,
    ) -> None:
        self.screenshot = screenshot
        self.on_selected = on_selected
        self.on_cancelled = on_cancelled
        self.start: tuple[int, int] | None = None
        self.end: tuple[int, int] | None = None
        self.closed = False

        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        width, height = screenshot.size
        self.window.geometry(f"{width}x{height}{origin_x:+d}{origin_y:+d}")

        self.canvas = tk.Canvas(
            self.window,
            width=width,
            height=height,
            highlightthickness=0,
            borderwidth=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self.photo = ImageTk.PhotoImage(screenshot)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

        self.masks = [
            self.canvas.create_rectangle(
                0,
                0,
                width,
                height,
                fill=self.MASK_COLOR,
                stipple="gray50",
                outline="",
            )
            for _ in range(4)
        ]
        self.selection_box = self.canvas.create_rectangle(
            0, 0, 0, 0, outline=self.ACCENT, width=2, state="hidden"
        )
        self.size_box = self.canvas.create_rectangle(
            0, 0, 0, 0, fill="#0f172a", outline="", state="hidden"
        )
        self.size_text = self.canvas.create_text(
            0,
            0,
            text="",
            fill="white",
            font=("Segoe UI", 10),
            state="hidden",
        )

        hint_width = 410
        center = width // 2
        self.canvas.create_rectangle(
            center - hint_width // 2,
            22,
            center + hint_width // 2,
            66,
            fill="#0f172a",
            outline="#334155",
            width=1,
        )
        self.canvas.create_text(
            center,
            44,
            text="拖动鼠标框选识别区域  ·  Esc / 右键取消",
            fill="white",
            font=("Microsoft YaHei UI", 11),
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", lambda _event: self.cancel())
        self.window.bind("<Escape>", lambda _event: self.cancel())

        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _point(self, event) -> tuple[int, int]:
        width, height = self.screenshot.size
        return (
            max(0, min(width, int(event.x))),
            max(0, min(height, int(event.y))),
        )

    def _on_press(self, event) -> None:
        self.start = self._point(event)
        self.end = self.start
        self._redraw()

    def _on_drag(self, event) -> None:
        if self.start is None:
            return
        self.end = self._point(event)
        self._redraw()

    def _on_release(self, event) -> None:
        if self.start is None:
            return
        self.end = self._point(event)
        x1, y1, x2, y2 = self._ordered_box()
        if x2 - x1 < 8 or y2 - y1 < 8:
            self.start = None
            self.end = None
            self._reset_mask()
            return

        crop = self.screenshot.crop((x1, y1, x2, y2))
        self.closed = True
        self.window.destroy()
        self.on_selected(crop)

    def _ordered_box(self) -> tuple[int, int, int, int]:
        assert self.start is not None and self.end is not None
        return (
            min(self.start[0], self.end[0]),
            min(self.start[1], self.end[1]),
            max(self.start[0], self.end[0]),
            max(self.start[1], self.end[1]),
        )

    def _reset_mask(self) -> None:
        width, height = self.screenshot.size
        self.canvas.itemconfigure(self.masks[0], state="normal")
        self.canvas.coords(self.masks[0], 0, 0, width, height)
        for item in self.masks[1:]:
            self.canvas.itemconfigure(item, state="hidden")
        for item in (self.selection_box, self.size_box, self.size_text):
            self.canvas.itemconfigure(item, state="hidden")

    def _redraw(self) -> None:
        if self.start is None or self.end is None:
            return
        width, height = self.screenshot.size
        x1, y1, x2, y2 = self._ordered_box()

        mask_boxes = (
            (0, 0, width, y1),
            (0, y1, x1, y2),
            (x2, y1, width, y2),
            (0, y2, width, height),
        )
        for item, box in zip(self.masks, mask_boxes):
            self.canvas.itemconfigure(item, state="normal")
            self.canvas.coords(item, *box)

        self.canvas.itemconfigure(self.selection_box, state="normal")
        self.canvas.coords(self.selection_box, x1, y1, x2, y2)

        label = f"{x2 - x1} × {y2 - y1}"
        label_x = min(max(x1 + 50, 55), width - 55)
        label_y = y1 - 17 if y1 > 42 else min(height - 17, y2 + 17)
        self.canvas.itemconfigure(self.size_box, state="normal")
        self.canvas.coords(self.size_box, label_x - 48, label_y - 13, label_x + 48, label_y + 13)
        self.canvas.itemconfigure(self.size_text, state="normal", text=label)
        self.canvas.coords(self.size_text, label_x, label_y)

    def cancel(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.window.destroy()
        self.on_cancelled()


class ScreenshotOcrApp:
    BG = "#f1f5f9"
    CARD = "#ffffff"
    TEXT = "#0f172a"
    MUTED = "#64748b"
    ACCENT = "#16a34a"
    ACCENT_ACTIVE = "#15803d"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        try:
            self.settings.autostart = is_autostart_enabled()
        except OSError:
            self.settings.autostart = False
        self.busy = False
        self.capture_active = False
        self.hotkey_latched = False
        self.capture_mode = "ocr"
        self.return_to_background = False
        self.is_quitting = False
        self.overlay: SelectionOverlay | None = None
        self.last_image: Image.Image | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.language_map: dict[str, str | None] = {}
        self.pin_windows: list[PinWindow] = []
        self.tray_icon: pystray.Icon | None = None
        self.tray_thread: threading.Thread | None = None
        self.settings_dialog: SettingsDialog | None = None

        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("820x720")
        self.root.minsize(700, 600)
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.attributes("-topmost", self.settings.always_on_top)

        icon = resource_path("assets/app.ico")
        if icon.exists():
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

        self._configure_styles()
        self._build_ui()
        self._load_languages()
        self.root.after(80, self._poll_hotkey)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TCombobox", padding=5, font=("Microsoft YaHei UI", 10))
        style.configure("TCheckbutton", background=self.CARD, font=("Microsoft YaHei UI", 9))
        style.map("TCheckbutton", background=[("active", self.CARD)])

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=24, pady=20)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(3, weight=1)

        header = tk.Frame(outer, bg=self.BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        title_wrap = tk.Frame(header, bg=self.BG)
        title_wrap.pack(side="left")
        tk.Label(
            title_wrap,
            text="截图 OCR",
            bg=self.BG,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_wrap,
            text="框选屏幕上的文字，本地识别并自动复制",
            bg=self.BG,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(3, 0))

        header_actions = tk.Frame(header, bg=self.BG)
        header_actions.pack(side="right", pady=5)

        self.settings_button = tk.Button(
            header_actions,
            text="⚙  设置",
            command=self.show_settings,
            bg="#e2e8f0",
            activebackground="#cbd5e1",
            fg="#334155",
            activeforeground=self.TEXT,
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10),
            padx=12,
            pady=11,
        )
        self.settings_button.pack(side="right", padx=(8, 0))

        self.capture_menu = tk.Menu(self.root, tearoff=False, font=("Microsoft YaHei UI", 9))
        self.capture_menu.add_command(label="截图并识别文字", command=lambda: self.begin_capture("ocr"))
        self.capture_menu.add_command(label="截图并编辑", command=lambda: self.begin_capture("edit"))
        self.capture_menu.add_command(label="截图后贴图", command=lambda: self.begin_capture("pin"))
        self.capture_menu.add_command(label="截图并保存", command=lambda: self.begin_capture("save"))
        self.capture_menu.add_command(label="截图并复制图片", command=lambda: self.begin_capture("copy"))
        self.capture_menu_button = tk.Button(
            header_actions,
            text="▾",
            command=self._show_capture_menu,
            bg=self.ACCENT,
            activebackground=self.ACCENT_ACTIVE,
            fg="white",
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI", 12, "bold"),
            padx=9,
            pady=10,
        )
        self.capture_menu_button.pack(side="right")

        self.capture_button = tk.Button(
            header_actions,
            text="＋  截图识别",
            command=lambda: self.begin_capture("ocr"),
            bg=self.ACCENT,
            activebackground=self.ACCENT_ACTIVE,
            fg="white",
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 11, "bold"),
            padx=20,
            pady=11,
        )
        self.capture_button.pack(side="right")

        settings = tk.Frame(outer, bg=self.CARD, highlightthickness=1, highlightbackground="#e2e8f0")
        settings.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        settings_inner = tk.Frame(settings, bg=self.CARD)
        settings_inner.pack(fill="x", padx=16, pady=12)

        tk.Label(
            settings_inner,
            text="识别语言",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        self.language_var = tk.StringVar(value="自动（系统首选）")
        self.language_combo = ttk.Combobox(
            settings_inner,
            textvariable=self.language_var,
            state="readonly",
            width=24,
        )
        self.language_combo.pack(side="left", padx=(9, 20))

        self.enhance_var = tk.BooleanVar(value=self.settings.enhance_small_text)
        ttk.Checkbutton(
            settings_inner,
            text="增强小字",
            variable=self.enhance_var,
            command=self._quick_settings_changed,
        ).pack(side="left", padx=(0, 16))
        self.autocopy_var = tk.BooleanVar(value=self.settings.auto_copy_text)
        ttk.Checkbutton(
            settings_inner,
            text="识别后自动复制",
            variable=self.autocopy_var,
            command=self._quick_settings_changed,
        ).pack(side="left")

        self.topmost_var = tk.BooleanVar(value=self.settings.always_on_top)
        ttk.Checkbutton(
            settings_inner,
            text="窗口置顶",
            variable=self.topmost_var,
            command=self._quick_settings_changed,
        ).pack(side="right")

        preview_card = tk.Frame(outer, bg=self.CARD, highlightthickness=1, highlightbackground="#e2e8f0")
        preview_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        preview_header = tk.Frame(preview_card, bg=self.CARD)
        preview_header.pack(fill="x", padx=16, pady=(11, 7))
        tk.Label(
            preview_header,
            text="截图预览",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left")
        self.image_info = tk.Label(
            preview_header,
            text="尚未截图",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        )
        self.image_info.pack(side="right")
        self.image_buttons: list[tk.Button] = []
        for label, command in (
            ("复制图片", self.copy_last_image),
            ("保存图片", self.save_last_image),
            ("贴图", self.pin_last_image),
            ("编辑", self.edit_last_image),
        ):
            button = self._small_button(preview_header, label, command)
            button.configure(state="disabled")
            button.pack(side="right", padx=(0, 6))
            self.image_buttons.append(button)
        self.preview = tk.Canvas(
            preview_card,
            height=145,
            bg="#e8edf3",
            highlightthickness=0,
        )
        self.preview.pack(fill="x", padx=16, pady=(0, 14))
        self.preview.create_text(
            10,
            72,
            text=f"点击“截图识别”或按 {self.settings.hotkey}",
            fill=self.MUTED,
            font=("Microsoft YaHei UI", 10),
            anchor="w",
            tags="placeholder",
        )

        result_card = tk.Frame(outer, bg=self.CARD, highlightthickness=1, highlightbackground="#e2e8f0")
        result_card.grid(row=3, column=0, sticky="nsew")
        result_header = tk.Frame(result_card, bg=self.CARD)
        result_header.pack(fill="x", padx=16, pady=(11, 7))
        tk.Label(
            result_header,
            text="识别结果",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left")

        self.clear_button = self._small_button(result_header, "清空", self.clear_result)
        self.clear_button.pack(side="right")
        self.save_button = self._small_button(result_header, "保存", self.save_result)
        self.save_button.pack(side="right", padx=(0, 7))
        self.copy_button = self._small_button(result_header, "复制", self.copy_result)
        self.copy_button.pack(side="right", padx=(0, 7))

        text_wrap = tk.Frame(result_card, bg="#f8fafc", highlightthickness=1, highlightbackground="#e2e8f0")
        text_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        scrollbar = ttk.Scrollbar(text_wrap, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.result_text = tk.Text(
            text_wrap,
            wrap="word",
            undo=True,
            borderwidth=0,
            highlightthickness=0,
            bg="#f8fafc",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            selectbackground="#bbf7d0",
            selectforeground=self.TEXT,
            font=("Microsoft YaHei UI", 11),
            padx=11,
            pady=10,
            yscrollcommand=scrollbar.set,
        )
        self.result_text.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.result_text.yview)
        self.result_text.bind("<Control-a>", self._select_all)

        footer = tk.Frame(outer, bg=self.BG)
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.status_label = tk.Label(
            footer,
            text="●  就绪",
            bg=self.BG,
            fg=self.ACCENT,
            font=("Microsoft YaHei UI", 9),
        )
        self.status_label.pack(side="left")
        tk.Label(
            footer,
            text="Windows 本地识别 · 图片不会上传",
            bg=self.BG,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="right")

    def _small_button(self, parent, text: str, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#f1f5f9",
            activebackground="#e2e8f0",
            fg="#334155",
            activeforeground=self.TEXT,
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
            padx=11,
            pady=4,
        )

    def _show_capture_menu(self) -> None:
        x = self.capture_button.winfo_rootx()
        y = self.capture_button.winfo_rooty() + self.capture_button.winfo_height()
        self.capture_menu.tk_popup(x, y)

    def show_settings(self) -> None:
        self.show_main()
        if self.settings_dialog and self.settings_dialog.window.winfo_exists():
            self.settings_dialog.window.lift()
            self.settings_dialog.window.focus_force()
            return
        self.settings_dialog = SettingsDialog(self.root, self.settings, self._settings_saved)

    def _settings_saved(self, settings: AppSettings) -> None:
        previous_autostart = self.settings.autostart
        try:
            set_autostart(settings.autostart)
        except OSError as exc:
            settings.autostart = previous_autostart
            messagebox.showerror(
                APP_NAME,
                f"开机自启设置失败，其他设置仍会保存。\n\n{exc}",
                parent=self.root,
            )
        self.settings = settings
        self.enhance_var.set(settings.enhance_small_text)
        self.autocopy_var.set(settings.auto_copy_text)
        self.topmost_var.set(settings.always_on_top)
        self.root.attributes("-topmost", settings.always_on_top)
        self._save_settings_safely()
        self._set_status("设置已保存")

    def _quick_settings_changed(self) -> None:
        self.settings.enhance_small_text = self.enhance_var.get()
        self.settings.auto_copy_text = self.autocopy_var.get()
        self.settings.always_on_top = self.topmost_var.get()
        self.root.attributes("-topmost", self.settings.always_on_top)
        self._save_settings_safely()

    def _save_settings_safely(self) -> None:
        try:
            self.settings_store.save(self.settings)
        except OSError as exc:
            self._set_status(f"设置保存失败：{exc}", "#dc2626")

    def _load_languages(self) -> None:
        auto_label = "自动（系统首选）"
        self.language_map = {auto_label: None}
        try:
            for language in available_languages():
                label = f"{language.name}  ·  {language.tag}"
                self.language_map[label] = language.tag
        except Exception:
            pass
        self.language_combo.configure(values=list(self.language_map))
        self.language_var.set(auto_label)

    def _set_status(self, text: str, color: str | None = None) -> None:
        self.status_label.configure(text=f"●  {text}", fg=color or self.ACCENT)

    def begin_capture(self, mode: str | None = None) -> None:
        if self.busy or self.capture_active:
            return
        self.capture_mode = mode or self.settings.default_capture_action
        self.return_to_background = self.root.state() == "withdrawn"
        self.capture_active = True
        self._set_status("准备截图…", "#0284c7")
        self.root.withdraw()
        self.root.after(250, self._take_screenshot)

    def _take_screenshot(self) -> None:
        try:
            screenshot = ImageGrab.grab(all_screens=True)
            user32 = ctypes.windll.user32
            origin_x = user32.GetSystemMetrics(76)
            origin_y = user32.GetSystemMetrics(77)
            self.overlay = SelectionOverlay(
                self.root,
                screenshot,
                origin_x,
                origin_y,
                self._selection_done,
                self._selection_cancelled,
            )
            self._set_status("正在框选", "#0284c7")
        except Exception as exc:
            self.capture_active = False
            self.root.deiconify()
            self._set_status("截图失败", "#dc2626")
            messagebox.showerror(APP_NAME, f"无法截取屏幕：\n{exc}", parent=self.root)

    def _selection_cancelled(self) -> None:
        self.overlay = None
        self.capture_active = False
        if self.return_to_background:
            self.root.withdraw()
        else:
            self.show_main()
        self._set_status("已取消")

    def _selection_done(self, image: Image.Image) -> None:
        self.overlay = None
        self.capture_active = False
        show_main = self.capture_mode in {"ocr", "edit", "save"} or not self.return_to_background
        if show_main:
            self.show_main()
        else:
            self.root.withdraw()
        self.last_image = image.copy()
        self._show_preview(image)
        self._dispatch_capture_action(image)

    def _dispatch_capture_action(self, image: Image.Image) -> None:
        if self.capture_mode == "edit":
            self.open_editor(image)
            self._set_status("已打开图片编辑器")
        elif self.capture_mode == "pin":
            self.pin_image(image)
            self._set_status("贴图已置顶；滚轮缩放，右键可关闭")
        elif self.capture_mode == "save":
            self.save_image(image)
            if self.return_to_background:
                self.root.withdraw()
        elif self.capture_mode == "copy":
            self.copy_image(image)
        else:
            self._start_ocr(image)

    def _show_preview(self, image: Image.Image) -> None:
        self.root.update_idletasks()
        canvas_width = max(200, self.preview.winfo_width())
        canvas_height = max(80, self.preview.winfo_height())
        scale = min(canvas_width / image.width, canvas_height / image.height, 1.0)
        shown = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        self.preview_photo = ImageTk.PhotoImage(shown)
        self.preview.delete("all")
        self.preview.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.preview_photo,
            anchor="center",
        )
        self.image_info.configure(text=f"{image.width} × {image.height} px")
        for button in self.image_buttons:
            button.configure(state="normal")

    def copy_image(self, image: Image.Image) -> bool:
        try:
            copy_image_to_clipboard(image)
            self._set_status("图片已复制到剪贴板")
            return True
        except OSError as exc:
            self._set_status("复制图片失败", "#dc2626")
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)
            return False

    def copy_last_image(self) -> None:
        if self.last_image is not None:
            self.copy_image(self.last_image)

    def save_image(self, image: Image.Image) -> Path | None:
        path = save_image_dialog(
            self.root,
            image,
            self.settings.default_save_dir,
            self.settings.image_format,
        )
        if path:
            self._set_status(f"图片已保存：{path.name}")
            return path
        self._set_status("已取消保存")
        return None

    def save_last_image(self) -> None:
        if self.last_image is not None:
            self.save_image(self.last_image)

    def pin_image(self, image: Image.Image) -> None:
        pin = PinWindow(
            self.root,
            image,
            self.settings.default_save_dir,
            self.settings.image_format,
            self.open_editor,
            self._remove_pin,
            self._set_status,
        )
        self.pin_windows.append(pin)

    def pin_last_image(self) -> None:
        if self.last_image is not None:
            self.pin_image(self.last_image)
            self._set_status("贴图已置顶；滚轮缩放，右键可关闭")

    def _remove_pin(self, pin: PinWindow) -> None:
        if pin in self.pin_windows:
            self.pin_windows.remove(pin)

    def open_editor(self, image: Image.Image) -> None:
        ImageEditor(
            self.root,
            image,
            self.settings.default_save_dir,
            self.settings.image_format,
            self._editor_applied,
            self.pin_image,
            self._editor_ocr,
            self._set_status,
        )

    def edit_last_image(self) -> None:
        if self.last_image is not None:
            self.open_editor(self.last_image)

    def _editor_applied(self, image: Image.Image) -> None:
        self.last_image = image.copy()
        self._show_preview(image)
        self._set_status("编辑结果已应用")

    def _editor_ocr(self, image: Image.Image) -> None:
        if self.busy:
            return
        self.last_image = image.copy()
        self.show_main()
        self._show_preview(image)
        self._start_ocr(image)

    def _start_ocr(self, image: Image.Image) -> None:
        self.busy = True
        self.capture_button.configure(state="disabled", text="正在识别…", bg="#94a3b8")
        self.capture_menu_button.configure(state="disabled", bg="#94a3b8")
        self._set_status("正在本地识别…", "#0284c7")
        language = self.language_map.get(self.language_var.get())
        enhance = self.enhance_var.get()

        def work() -> None:
            try:
                text = recognize_image(image, language, enhance)
                self.root.after(0, lambda: self._ocr_finished(text))
            except Exception as exc:
                details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                self.root.after(0, lambda: self._ocr_failed(details))

        threading.Thread(target=work, daemon=True, name="ocr-worker").start()

    def _ocr_finished(self, text: str) -> None:
        self.busy = False
        self.capture_button.configure(state="normal", text="＋  截图识别", bg=self.ACCENT)
        self.capture_menu_button.configure(state="normal", bg=self.ACCENT)
        self.result_text.delete("1.0", "end")
        if text:
            self.result_text.insert("1.0", text)
            if self.autocopy_var.get():
                self._copy_text(text, quiet=True)
                self._set_status("识别完成，已复制")
            else:
                self._set_status("识别完成")
        else:
            self._set_status("未识别到文字", "#d97706")
            self.result_text.insert("1.0", "未识别到文字。请尝试扩大框选范围或开启“增强小字”。")

    def _ocr_failed(self, details: str) -> None:
        self.busy = False
        self.capture_button.configure(state="normal", text="＋  截图识别", bg=self.ACCENT)
        self.capture_menu_button.configure(state="normal", bg=self.ACCENT)
        self._set_status("识别失败", "#dc2626")
        messagebox.showerror(
            APP_NAME,
            "OCR 识别失败。请确认 Windows 已安装所选语言的 OCR 语言包。\n\n" + details,
            parent=self.root,
        )

    def _copy_text(self, text: str, quiet: bool = False) -> None:
        if not text.strip():
            if not quiet:
                self._set_status("没有可复制的内容", "#d97706")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        if not quiet:
            self._set_status("已复制到剪贴板")

    def copy_result(self) -> None:
        self._copy_text(self.result_text.get("1.0", "end-1c"))

    def clear_result(self) -> None:
        self.result_text.delete("1.0", "end")
        self._set_status("已清空")

    def save_result(self) -> None:
        text = self.result_text.get("1.0", "end-1c").strip()
        if not text:
            self._set_status("没有可保存的内容", "#d97706")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="保存 OCR 文字",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=f"OCR_{datetime.now():%Y%m%d_%H%M%S}.txt",
        )
        if not path:
            return
        Path(path).write_text(text, encoding="utf-8-sig")
        self._set_status("结果已保存")

    def _select_all(self, _event):
        self.result_text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def on_close(self) -> None:
        action = self.settings.close_action
        if action == "tray":
            self.hide_to_tray()
            return
        if action == "exit":
            self.exit_app()
            return

        choice = messagebox.askyesnocancel(
            "关闭截图 OCR",
            "是否让截图 OCR 在后台运行？\n\n"
            f"选择“是”：隐藏到系统托盘，仍可使用 {self.settings.hotkey}\n"
            "选择“否”：彻底退出程序\n"
            "选择“取消”：返回主窗口",
            parent=self.root,
            icon="question",
        )
        if choice is True:
            self.hide_to_tray()
        elif choice is False:
            self.exit_app()

    def hide_to_tray(self) -> None:
        self._start_tray()
        self.root.withdraw()
        self._set_status(f"正在后台运行；按 {self.settings.hotkey} 截图")

    def show_main(self) -> None:
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def _start_tray(self) -> None:
        if self.tray_icon is not None:
            return
        icon_image = Image.open(resource_path("assets/app.ico")).convert("RGBA")

        def ui(callback):
            return lambda _icon, _item: self.root.after(0, callback)

        menu = pystray.Menu(
            pystray.MenuItem("显示主窗口", ui(self.show_main), default=True),
            pystray.MenuItem("截图", ui(lambda: self.begin_capture())),
            pystray.MenuItem("截图识别", ui(lambda: self.begin_capture("ocr"))),
            pystray.MenuItem("设置", ui(self.show_settings)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", ui(self.exit_app)),
        )
        self.tray_icon = pystray.Icon("ScreenshotOCR", icon_image, APP_NAME, menu)
        self.tray_thread = threading.Thread(
            target=self.tray_icon.run,
            daemon=True,
            name="system-tray",
        )
        self.tray_thread.start()

    def exit_app(self) -> None:
        if self.is_quitting:
            return
        self.is_quitting = True
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _hotkey_codes(self) -> tuple[int, ...]:
        key_codes = {
            "Ctrl": 0x11,
            "Alt": 0x12,
            "Shift": 0x10,
            "O": 0x4F,
            "S": 0x53,
        }
        return tuple(key_codes[part] for part in self.settings.hotkey.split("+") if part in key_codes)

    def _poll_hotkey(self) -> None:
        try:
            user32 = ctypes.windll.user32
            pressed = all(
                user32.GetAsyncKeyState(key) & 0x8000
                for key in self._hotkey_codes()
            )
            if pressed and not self.hotkey_latched and not self.busy and not self.capture_active:
                self.hotkey_latched = True
                self.begin_capture()
            elif not pressed:
                self.hotkey_latched = False
        finally:
            try:
                self.root.after(70, self._poll_hotkey)
            except tk.TclError:
                pass


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        raise SystemExit(run_packaged_self_test(Path(sys.argv[2])))
    enable_high_dpi()
    if not acquire_single_instance():
        return
    root = tk.Tk()
    app = ScreenshotOcrApp(root)
    if "--background" in sys.argv:
        root.after(0, app.hide_to_tray)
    root.mainloop()


if __name__ == "__main__":
    main()
