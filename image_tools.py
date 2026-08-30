from __future__ import annotations

import ctypes
import io
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

from PIL import Image


def copy_image_to_clipboard(image: Image.Image) -> None:
    """将 PIL 图片写入 Windows 剪贴板（CF_DIB）。"""

    bmp = io.BytesIO()
    image.convert("RGB").save(bmp, format="BMP")
    dib = bmp.getvalue()[14:]

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    global_memory = kernel32.GlobalAlloc(0x0002, len(dib))  # GMEM_MOVEABLE
    if not global_memory:
        raise OSError("无法分配剪贴板内存")

    locked = kernel32.GlobalLock(global_memory)
    if not locked:
        kernel32.GlobalFree(global_memory)
        raise OSError("无法锁定剪贴板内存")
    ctypes.memmove(locked, dib, len(dib))
    kernel32.GlobalUnlock(global_memory)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(global_memory)
        raise OSError("剪贴板正被其他程序占用")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(8, global_memory):  # CF_DIB
            raise OSError("无法写入图片到剪贴板")
        global_memory = None  # 成功后由系统接管
    finally:
        user32.CloseClipboard()
        if global_memory:
            kernel32.GlobalFree(global_memory)


def save_image_dialog(
    parent: tk.Misc,
    image: Image.Image,
    default_dir: str,
    image_format: str = "PNG",
) -> Path | None:
    selected_format = image_format if image_format in {"PNG", "JPG"} else "PNG"
    extension = ".png" if selected_format == "PNG" else ".jpg"
    file_types = [("PNG 图片", "*.png"), ("JPEG 图片", "*.jpg;*.jpeg"), ("所有文件", "*.*")]
    path = filedialog.asksaveasfilename(
        parent=parent,
        title="保存截图",
        initialdir=default_dir or None,
        initialfile=f"Screenshot_{datetime.now():%Y%m%d_%H%M%S}{extension}",
        defaultextension=extension,
        filetypes=file_types,
    )
    if not path:
        return None

    target = Path(path)
    fmt = "JPEG" if target.suffix.lower() in {".jpg", ".jpeg"} else "PNG"
    output = image.convert("RGB") if fmt == "JPEG" else image
    save_options = {"quality": 94, "subsampling": 0} if fmt == "JPEG" else {"optimize": True}
    output.save(target, format=fmt, **save_options)
    return target
