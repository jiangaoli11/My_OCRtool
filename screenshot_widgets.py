from __future__ import annotations

import math
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from image_tools import copy_image_to_clipboard, save_image_dialog


class PinWindow:
    """无边框置顶贴图，支持拖动、缩放和右键操作。"""

    def __init__(
        self,
        root: tk.Misc,
        image: Image.Image,
        default_dir: str,
        image_format: str,
        on_edit,
        on_close,
        on_status,
    ) -> None:
        self.root = root
        self.image = image.copy()
        self.default_dir = default_dir
        self.image_format = image_format
        self.on_edit = on_edit
        self.on_close = on_close
        self.on_status = on_status
        self.zoom = min(1.0, 620 / image.width, 460 / image.height)
        self.zoom = max(0.12, self.zoom)
        self.photo: ImageTk.PhotoImage | None = None
        self.drag_origin: tuple[int, int, int, int] | None = None

        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#22c55e", padx=2, pady=2)
        self.canvas = tk.Canvas(self.window, highlightthickness=0, borderwidth=0, bg="#0f172a")
        self.canvas.pack()

        self.menu = tk.Menu(self.window, tearoff=False, font=("Microsoft YaHei UI", 9))
        self.menu.add_command(label="复制图片", command=self.copy)
        self.menu.add_command(label="保存图片…", command=self.save)
        self.menu.add_command(label="打开编辑器", command=lambda: self.on_edit(self.image.copy()))
        self.menu.add_separator()
        self.menu.add_command(label="关闭贴图", command=self.close)

        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<Button-3>", self._show_menu)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.window.bind("<Escape>", lambda _event: self.close())
        self._render()

        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        self.window.update_idletasks()
        x = max(20, (screen_w - self.window.winfo_width()) // 2)
        y = max(20, (screen_h - self.window.winfo_height()) // 2)
        self.window.geometry(f"+{x}+{y}")

    def _render(self) -> None:
        width = max(1, round(self.image.width * self.zoom))
        height = max(1, round(self.image.height * self.zoom))
        shown = self.image.resize((width, height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(shown)
        self.canvas.configure(width=width, height=height)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

    def _start_drag(self, event) -> None:
        self.drag_origin = (event.x_root, event.y_root, self.window.winfo_x(), self.window.winfo_y())

    def _drag(self, event) -> None:
        if self.drag_origin is None:
            return
        start_x, start_y, window_x, window_y = self.drag_origin
        self.window.geometry(f"+{window_x + event.x_root - start_x}+{window_y + event.y_root - start_y}")

    def _wheel(self, event) -> None:
        old_zoom = self.zoom
        self.zoom = min(2.5, self.zoom * 1.1) if event.delta > 0 else max(0.12, self.zoom / 1.1)
        if abs(old_zoom - self.zoom) > 0.001:
            self._render()

    def _show_menu(self, event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)

    def copy(self) -> None:
        try:
            copy_image_to_clipboard(self.image)
            self.on_status("贴图已复制")
        except OSError as exc:
            messagebox.showerror("截图 OCR", str(exc), parent=self.window)

    def save(self) -> None:
        path = save_image_dialog(self.window, self.image, self.default_dir, self.image_format)
        if path:
            self.on_status(f"图片已保存：{path.name}")

    def close(self) -> None:
        try:
            self.window.destroy()
        finally:
            self.on_close(self)


class ImageEditor:
    TOOLS = (
        ("pen", "画笔"),
        ("rectangle", "矩形"),
        ("ellipse", "椭圆"),
        ("arrow", "箭头"),
        ("text", "文字"),
        ("mosaic", "马赛克"),
        ("crop", "裁剪"),
    )

    def __init__(
        self,
        root: tk.Misc,
        image: Image.Image,
        default_dir: str,
        image_format: str,
        on_apply,
        on_pin,
        on_ocr,
        on_status,
    ) -> None:
        self.root = root
        self.working = image.convert("RGBA")
        self.default_dir = default_dir
        self.image_format = image_format
        self.on_apply = on_apply
        self.on_pin = on_pin
        self.on_ocr = on_ocr
        self.on_status = on_status

        self.undo_stack: list[Image.Image] = []
        self.redo_stack: list[Image.Image] = []
        self.tool = "pen"
        self.color = "#ef4444"
        self.width_var = tk.IntVar(value=5)
        self.font_size_var = tk.IntVar(value=32)
        self.photo: ImageTk.PhotoImage | None = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.start_canvas: tuple[int, int] | None = None
        self.start_image: tuple[int, int] | None = None
        self.pen_points: list[tuple[int, int]] = []
        self.preview_item: int | None = None
        self.render_job: str | None = None
        self.tool_buttons: dict[str, tk.Button] = {}

        self.window = tk.Toplevel(root)
        self.window.title("图片编辑 - 截图 OCR")
        self.window.geometry("1100x760")
        self.window.minsize(800, 560)
        self.window.configure(bg="#0f172a")
        self.window.attributes("-topmost", True)
        self.window.after(200, self._release_topmost)

        self._build_ui()
        self.canvas.bind("<Configure>", self._schedule_render)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.window.bind("<Control-z>", lambda _event: self.undo())
        self.window.bind("<Control-y>", lambda _event: self.redo())
        self.window.bind("<Control-s>", lambda _event: self.save())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.after(80, self._render)

    def _release_topmost(self) -> None:
        try:
            if self.window.winfo_exists():
                self.window.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _build_ui(self) -> None:
        toolbar = tk.Frame(self.window, bg="#1e293b", padx=10, pady=8)
        toolbar.pack(fill="x")

        for tool, label in self.TOOLS:
            button = tk.Button(
                toolbar,
                text=label,
                command=lambda selected=tool: self.select_tool(selected),
                bg="#334155",
                activebackground="#475569",
                fg="white",
                activeforeground="white",
                relief="flat",
                borderwidth=0,
                padx=10,
                pady=6,
                cursor="hand2",
                font=("Microsoft YaHei UI", 9),
            )
            button.pack(side="left", padx=(0, 5))
            self.tool_buttons[tool] = button

        self.color_button = tk.Button(
            toolbar,
            text="颜色",
            command=self.choose_color,
            bg=self.color,
            activebackground=self.color,
            fg="white",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=6,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        self.color_button.pack(side="left", padx=(7, 5))

        tk.Label(toolbar, text="粗细", bg="#1e293b", fg="#cbd5e1", font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(4, 3))
        ttk.Combobox(
            toolbar,
            textvariable=self.width_var,
            values=(2, 3, 5, 8, 12, 18),
            state="readonly",
            width=3,
        ).pack(side="left")
        tk.Label(toolbar, text="字号", bg="#1e293b", fg="#cbd5e1", font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(9, 3))
        ttk.Combobox(
            toolbar,
            textvariable=self.font_size_var,
            values=(18, 24, 32, 48, 64),
            state="readonly",
            width=3,
        ).pack(side="left")

        self._toolbar_button(toolbar, "↶", self.undo).pack(side="right", padx=(5, 0))
        self._toolbar_button(toolbar, "↷", self.redo).pack(side="right", padx=(5, 0))
        self._toolbar_button(toolbar, "左转", lambda: self.rotate(90)).pack(side="right", padx=(5, 0))
        self._toolbar_button(toolbar, "右转", lambda: self.rotate(-90)).pack(side="right", padx=(5, 0))

        self.canvas = tk.Canvas(self.window, bg="#020617", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        bottom = tk.Frame(self.window, bg="#1e293b", padx=12, pady=9)
        bottom.pack(fill="x")
        self.hint_label = tk.Label(
            bottom,
            text="在图片上拖动进行标注 · Ctrl+Z 撤销 · Esc 关闭",
            bg="#1e293b",
            fg="#94a3b8",
            font=("Microsoft YaHei UI", 9),
        )
        self.hint_label.pack(side="left")
        self._action_button(bottom, "完成", self.apply, "#16a34a").pack(side="right")
        self._action_button(bottom, "OCR", lambda: self.on_ocr(self.working.copy()), "#0284c7").pack(side="right", padx=(0, 6))
        self._action_button(bottom, "贴图", lambda: self.on_pin(self.working.copy()), "#475569").pack(side="right", padx=(0, 6))
        self._action_button(bottom, "复制", self.copy, "#475569").pack(side="right", padx=(0, 6))
        self._action_button(bottom, "保存", self.save, "#475569").pack(side="right", padx=(0, 6))

        self.select_tool("pen")

    def _toolbar_button(self, parent, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#334155",
            activebackground="#475569",
            fg="white",
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=6,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )

    def _action_button(self, parent, text: str, command, color: str) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            activebackground=color,
            fg="white",
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            padx=15,
            pady=6,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )

    def select_tool(self, tool: str) -> None:
        self.tool = tool
        for name, button in self.tool_buttons.items():
            button.configure(bg="#16a34a" if name == tool else "#334155")
        hint = {
            "pen": "按住左键自由绘制",
            "rectangle": "拖动绘制矩形框",
            "ellipse": "拖动绘制椭圆",
            "arrow": "从起点拖向箭头方向",
            "text": "点击图片添加文字",
            "mosaic": "拖动选择要打码的区域",
            "crop": "拖动选择保留区域",
        }[tool]
        self.hint_label.configure(text=hint + " · Ctrl+Z 撤销")

    def choose_color(self) -> None:
        selected = colorchooser.askcolor(self.color, parent=self.window, title="选择标注颜色")[1]
        if selected:
            self.color = selected
            self.color_button.configure(bg=selected, activebackground=selected)

    def _schedule_render(self, _event=None) -> None:
        if self.render_job:
            self.window.after_cancel(self.render_job)
        self.render_job = self.window.after(80, self._render)

    def _render(self) -> None:
        self.render_job = None
        canvas_w = max(100, self.canvas.winfo_width())
        canvas_h = max(100, self.canvas.winfo_height())
        self.scale = min(canvas_w / self.working.width, canvas_h / self.working.height, 1.0)
        shown_w = max(1, round(self.working.width * self.scale))
        shown_h = max(1, round(self.working.height * self.scale))
        self.offset_x = (canvas_w - shown_w) // 2
        self.offset_y = (canvas_h - shown_h) // 2
        shown = self.working.resize((shown_w, shown_h), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(shown)
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.photo, anchor="nw", tags="image")
        self.canvas.create_rectangle(
            self.offset_x - 1,
            self.offset_y - 1,
            self.offset_x + shown_w,
            self.offset_y + shown_h,
            outline="#334155",
            width=1,
        )
        self.preview_item = None

    def _inside_image(self, x: int, y: int) -> bool:
        return (
            self.offset_x <= x <= self.offset_x + self.working.width * self.scale
            and self.offset_y <= y <= self.offset_y + self.working.height * self.scale
        )

    def _to_image(self, x: int, y: int) -> tuple[int, int]:
        image_x = round((x - self.offset_x) / self.scale)
        image_y = round((y - self.offset_y) / self.scale)
        return (
            max(0, min(self.working.width - 1, image_x)),
            max(0, min(self.working.height - 1, image_y)),
        )

    def _on_press(self, event) -> None:
        if not self._inside_image(event.x, event.y):
            return
        if self.tool == "text":
            self._add_text(self._to_image(event.x, event.y))
            return
        self.start_canvas = (event.x, event.y)
        self.start_image = self._to_image(event.x, event.y)
        self.pen_points = [self.start_image]

    def _on_motion(self, event) -> None:
        if self.start_canvas is None or self.start_image is None:
            return
        x = max(self.offset_x, min(round(self.offset_x + self.working.width * self.scale), event.x))
        y = max(self.offset_y, min(round(self.offset_y + self.working.height * self.scale), event.y))
        if self.tool == "pen":
            previous = self.pen_points[-1]
            current = self._to_image(x, y)
            self.pen_points.append(current)
            self.canvas.create_line(
                self.offset_x + previous[0] * self.scale,
                self.offset_y + previous[1] * self.scale,
                self.offset_x + current[0] * self.scale,
                self.offset_y + current[1] * self.scale,
                fill=self.color,
                width=max(1, self.width_var.get() * self.scale),
                capstyle="round",
                tags="preview",
            )
            return

        self.canvas.delete("preview")
        x1, y1 = self.start_canvas
        options = {
            "outline": self.color if self.tool not in {"crop", "mosaic"} else "#22c55e",
            "width": max(1, self.width_var.get() * self.scale),
            "dash": (6, 4) if self.tool in {"crop", "mosaic"} else (),
            "tags": "preview",
        }
        if self.tool in {"rectangle", "crop", "mosaic"}:
            self.preview_item = self.canvas.create_rectangle(x1, y1, x, y, **options)
        elif self.tool == "ellipse":
            self.preview_item = self.canvas.create_oval(x1, y1, x, y, **options)
        elif self.tool == "arrow":
            self.preview_item = self.canvas.create_line(
                x1,
                y1,
                x,
                y,
                fill=self.color,
                width=max(1, self.width_var.get() * self.scale),
                arrow="last",
                arrowshape=(14, 18, 7),
                tags="preview",
            )

    def _on_release(self, event) -> None:
        if self.start_image is None:
            return
        end = self._to_image(event.x, event.y)
        start = self.start_image
        self.start_canvas = None
        self.start_image = None
        if abs(end[0] - start[0]) < 2 and abs(end[1] - start[1]) < 2:
            self.canvas.delete("preview")
            return

        self._push_undo()
        draw = ImageDraw.Draw(self.working)
        width = self.width_var.get()
        box = (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
        if self.tool == "pen":
            if len(self.pen_points) > 1:
                draw.line(self.pen_points, fill=self.color, width=width, joint="curve")
        elif self.tool == "rectangle":
            draw.rectangle(box, outline=self.color, width=width)
        elif self.tool == "ellipse":
            draw.ellipse(box, outline=self.color, width=width)
        elif self.tool == "arrow":
            self._draw_arrow(draw, start, end, self.color, width)
        elif self.tool == "mosaic":
            self._mosaic(box)
        elif self.tool == "crop":
            self.working = self.working.crop((box[0], box[1], box[2] + 1, box[3] + 1))
        self.pen_points = []
        self._render()

    def _push_undo(self) -> None:
        self.undo_stack.append(self.working.copy())
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(self.working.copy())
        self.working = self.undo_stack.pop()
        self._render()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(self.working.copy())
        self.working = self.redo_stack.pop()
        self._render()

    def rotate(self, degrees: int) -> None:
        self._push_undo()
        self.working = self.working.rotate(degrees, expand=True)
        self._render()

    def _add_text(self, point: tuple[int, int]) -> None:
        text = simpledialog.askstring("添加文字", "请输入要添加的文字：", parent=self.window)
        if not text:
            return
        self._push_undo()
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", self.font_size_var.get())
        except OSError:
            font = ImageFont.load_default()
        ImageDraw.Draw(self.working).multiline_text(point, text, fill=self.color, font=font, spacing=5)
        self._render()

    @staticmethod
    def _draw_arrow(draw: ImageDraw.ImageDraw, start, end, color: str, width: int) -> None:
        draw.line((start, end), fill=color, width=width)
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        head = max(12, width * 4)
        spread = math.pi / 7
        left = (end[0] - head * math.cos(angle - spread), end[1] - head * math.sin(angle - spread))
        right = (end[0] - head * math.cos(angle + spread), end[1] - head * math.sin(angle + spread))
        draw.polygon((end, left, right), fill=color)

    def _mosaic(self, box: tuple[int, int, int, int]) -> None:
        x1, y1, x2, y2 = box
        region = self.working.crop((x1, y1, x2 + 1, y2 + 1))
        block = max(6, self.width_var.get() * 2)
        small = region.resize(
            (max(1, region.width // block), max(1, region.height // block)),
            Image.Resampling.BILINEAR,
        )
        pixelated = small.resize(region.size, Image.Resampling.NEAREST)
        self.working.paste(pixelated, (x1, y1))

    def save(self) -> None:
        path = save_image_dialog(self.window, self.working, self.default_dir, self.image_format)
        if path:
            self.on_status(f"图片已保存：{path.name}")

    def copy(self) -> None:
        try:
            copy_image_to_clipboard(self.working)
            self.on_status("图片已复制到剪贴板")
        except OSError as exc:
            messagebox.showerror("截图 OCR", str(exc), parent=self.window)

    def apply(self) -> None:
        self.on_apply(self.working.copy())
        self.window.destroy()
