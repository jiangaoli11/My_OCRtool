from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class AppSettings:
    close_action: str = "ask"
    default_save_dir: str = ""
    image_format: str = "PNG"
    default_capture_action: str = "ocr"
    auto_copy_text: bool = True
    enhance_small_text: bool = True
    always_on_top: bool = False
    autostart: bool = False
    hotkey: str = "Ctrl+Alt+O"

    def __post_init__(self) -> None:
        if not self.default_save_dir:
            pictures = Path.home() / "Pictures"
            self.default_save_dir = str(pictures / "Screenshots")


class SettingsStore:
    def __init__(self) -> None:
        app_data = Path(os.environ.get("APPDATA", Path.home()))
        self.path = app_data / "ScreenshotOCR" / "settings.json"

    def load(self) -> AppSettings:
        defaults = AppSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = {item.name for item in fields(AppSettings)}
            values = {key: value for key, value in raw.items() if key in allowed}
            settings = AppSettings(**values)
        except (OSError, ValueError, TypeError):
            return defaults

        if settings.close_action not in {"ask", "tray", "exit"}:
            settings.close_action = defaults.close_action
        if settings.image_format not in {"PNG", "JPG"}:
            settings.image_format = defaults.image_format
        if settings.default_capture_action not in {"ocr", "edit", "pin", "save", "copy"}:
            settings.default_capture_action = defaults.default_capture_action
        if settings.hotkey not in {"Ctrl+Alt+O", "Ctrl+Shift+O", "Ctrl+Alt+S", "Ctrl+Shift+S"}:
            settings.hotkey = defaults.hotkey
        return settings

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
