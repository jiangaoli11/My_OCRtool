from __future__ import annotations

import sys
import winreg
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ScreenshotOCR"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        return f'"{executable}" --background'

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve().with_name("app.py")
    return f'"{pythonw}" "{script}" --background'


def set_autostart(enabled: bool) -> None:
    """配置当前 Windows 用户的开机启动项，不需要管理员权限。"""

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            command, value_type = winreg.QueryValueEx(key, VALUE_NAME)
        return value_type == winreg.REG_SZ and bool(command)
    except FileNotFoundError:
        return False
