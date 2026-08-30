from __future__ import annotations

from dataclasses import replace
import tkinter as tk
from tkinter import filedialog, ttk

from settings_store import AppSettings


class SettingsDialog:
    CLOSE_ACTIONS = {
        "每次询问": "ask",
        "关闭时转到后台": "tray",
        "关闭时直接退出": "exit",
    }
    CAPTURE_ACTIONS = {
        "OCR 识别文字": "ocr",
        "打开图片编辑器": "edit",
        "贴图到桌面": "pin",
        "保存图片": "save",
        "复制图片": "copy",
    }

    def __init__(self, parent: tk.Misc, settings: AppSettings, on_save) -> None:
        self.parent = parent
        self.settings = replace(settings)
        self.on_save = on_save

        self.window = tk.Toplevel(parent)
        self.window.title("设置 - 截图 OCR")
        dialog_height = max(560, min(720, int(parent.winfo_screenheight() * 0.84)))
        self.window.geometry(f"600x{dialog_height}")
        self.window.minsize(560, 520)
        self.window.resizable(True, True)
        self.window.configure(bg="#f1f5f9")
        self.window.transient(parent)
        self.window.grab_set()

        self.close_var = tk.StringVar(value=self._label_for(self.CLOSE_ACTIONS, settings.close_action))
        self.action_var = tk.StringVar(value=self._label_for(self.CAPTURE_ACTIONS, settings.default_capture_action))
        self.hotkey_var = tk.StringVar(value=settings.hotkey)
        self.directory_var = tk.StringVar(value=settings.default_save_dir)
        self.format_var = tk.StringVar(value=settings.image_format)
        self.auto_copy_var = tk.BooleanVar(value=settings.auto_copy_text)
        self.enhance_var = tk.BooleanVar(value=settings.enhance_small_text)
        self.topmost_var = tk.BooleanVar(value=settings.always_on_top)
        self.autostart_var = tk.BooleanVar(value=settings.autostart)

        self._build()
        self.window.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.window.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.window.winfo_height()) // 2)
        x = max(0, min(parent.winfo_screenwidth() - self.window.winfo_width(), x))
        y = max(0, min(parent.winfo_screenheight() - self.window.winfo_height(), y))
        self.window.geometry(f"+{x}+{y}")
        self.window.focus_force()

    @staticmethod
    def _label_for(mapping: dict[str, str], value: str) -> str:
        return next((label for label, key in mapping.items() if key == value), next(iter(mapping)))

    def _build(self) -> None:
        # 操作按钮独立固定在底部，内容过高时只滚动中间区域。
        buttons = tk.Frame(self.window, bg="#f1f5f9", padx=22, pady=12)
        buttons.pack(side="bottom", fill="x")
        tk.Button(
            buttons,
            text="恢复默认",
            command=self._reset,
            bg="#e2e8f0",
            activebackground="#cbd5e1",
            fg="#334155",
            relief="flat",
            padx=15,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        tk.Button(
            buttons,
            text="取消",
            command=self.window.destroy,
            bg="#e2e8f0",
            activebackground="#cbd5e1",
            fg="#334155",
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        ).pack(side="right")
        self.save_button = tk.Button(
            buttons,
            text="保存设置",
            command=self._save,
            bg="#16a34a",
            activebackground="#15803d",
            fg="white",
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.save_button.pack(side="right", padx=(0, 8))

        scroll_host = tk.Frame(self.window, bg="#f1f5f9")
        scroll_host.pack(side="top", fill="both", expand=True)
        self.scroll_canvas = tk.Canvas(scroll_host, bg="#f1f5f9", highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=self.scroll_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)

        outer = tk.Frame(self.scroll_canvas, bg="#f1f5f9")
        self.content_window = self.scroll_canvas.create_window(0, 0, window=outer, anchor="nw")
        outer.bind(
            "<Configure>",
            lambda _event: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")),
        )
        self.scroll_canvas.bind(
            "<Configure>",
            lambda event: self.scroll_canvas.itemconfigure(self.content_window, width=event.width),
        )
        self.window.bind(
            "<MouseWheel>",
            lambda event: self.scroll_canvas.yview_scroll(-1 * int(event.delta / 120), "units"),
        )

        content = tk.Frame(outer, bg="#f1f5f9")
        content.pack(fill="both", expand=True, padx=22, pady=(18, 8))

        tk.Label(
            content,
            text="设置",
            bg="#f1f5f9",
            fg="#0f172a",
            font=("Microsoft YaHei UI", 19, "bold"),
        ).pack(anchor="w")
        tk.Label(
            content,
            text="调整后台行为、开机启动、快捷键和截图默认操作",
            bg="#f1f5f9",
            fg="#64748b",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(3, 13))

        behavior = self._section(content, "常规")
        self._combo_row(behavior, "关闭主窗口", self.close_var, tuple(self.CLOSE_ACTIONS))
        self._combo_row(behavior, "快捷键默认操作", self.action_var, tuple(self.CAPTURE_ACTIONS))
        self._combo_row(
            behavior,
            "全局快捷键",
            self.hotkey_var,
            ("Ctrl+Alt+O", "Ctrl+Shift+O", "Ctrl+Alt+S", "Ctrl+Shift+S"),
        )
        self._check_row(behavior, "开机自动启动并在后台运行", self.autostart_var)

        files = self._section(content, "图片保存")
        directory_row = tk.Frame(files, bg="white")
        directory_row.pack(fill="x", pady=5)
        tk.Label(directory_row, text="默认文件夹", width=15, anchor="w", bg="white", fg="#334155", font=("Microsoft YaHei UI", 9)).pack(side="left")
        tk.Entry(
            directory_row,
            textvariable=self.directory_var,
            relief="solid",
            borderwidth=1,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", fill="x", expand=True, ipady=5)
        tk.Button(
            directory_row,
            text="浏览",
            command=self._browse,
            bg="#e2e8f0",
            activebackground="#cbd5e1",
            fg="#334155",
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(7, 0))
        self._combo_row(files, "默认格式", self.format_var, ("PNG", "JPG"))

        recognition = self._section(content, "识别与窗口")
        self._check_row(recognition, "OCR 完成后自动复制文字", self.auto_copy_var)
        self._check_row(recognition, "自动放大并增强较小文字", self.enhance_var)
        self._check_row(recognition, "主窗口始终置顶", self.topmost_var)

    def _section(self, parent, title: str) -> tk.Frame:
        card = tk.Frame(parent, bg="white", highlightthickness=1, highlightbackground="#e2e8f0")
        card.pack(fill="x", pady=(0, 9))
        tk.Label(card, text=title, bg="white", fg="#0f172a", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", padx=13, pady=(9, 3))
        body = tk.Frame(card, bg="white")
        body.pack(fill="x", padx=13, pady=(0, 9))
        return body

    @staticmethod
    def _combo_row(parent, label: str, variable: tk.StringVar, values: tuple[str, ...]) -> None:
        row = tk.Frame(parent, bg="white")
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, width=15, anchor="w", bg="white", fg="#334155", font=("Microsoft YaHei UI", 9)).pack(side="left")
        ttk.Combobox(row, textvariable=variable, values=values, state="readonly", font=("Microsoft YaHei UI", 9)).pack(side="left", fill="x", expand=True)

    @staticmethod
    def _check_row(parent, label: str, variable: tk.BooleanVar) -> None:
        tk.Checkbutton(
            parent,
            text=label,
            variable=variable,
            bg="white",
            activebackground="white",
            fg="#334155",
            selectcolor="white",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        ).pack(fill="x", pady=3)

    def _browse(self) -> None:
        selected = filedialog.askdirectory(
            parent=self.window,
            title="选择默认截图文件夹",
            initialdir=self.directory_var.get() or None,
        )
        if selected:
            self.directory_var.set(selected)

    def _reset(self) -> None:
        defaults = AppSettings()
        self.close_var.set(self._label_for(self.CLOSE_ACTIONS, defaults.close_action))
        self.action_var.set(self._label_for(self.CAPTURE_ACTIONS, defaults.default_capture_action))
        self.hotkey_var.set(defaults.hotkey)
        self.directory_var.set(defaults.default_save_dir)
        self.format_var.set(defaults.image_format)
        self.auto_copy_var.set(defaults.auto_copy_text)
        self.enhance_var.set(defaults.enhance_small_text)
        self.topmost_var.set(defaults.always_on_top)
        self.autostart_var.set(defaults.autostart)

    def _save(self) -> None:
        self.settings.close_action = self.CLOSE_ACTIONS[self.close_var.get()]
        self.settings.default_capture_action = self.CAPTURE_ACTIONS[self.action_var.get()]
        self.settings.hotkey = self.hotkey_var.get()
        self.settings.default_save_dir = self.directory_var.get().strip() or AppSettings().default_save_dir
        self.settings.image_format = self.format_var.get()
        self.settings.auto_copy_text = self.auto_copy_var.get()
        self.settings.enhance_small_text = self.enhance_var.get()
        self.settings.always_on_top = self.topmost_var.get()
        self.settings.autostart = self.autostart_var.get()
        self.on_save(self.settings)
        self.window.destroy()
