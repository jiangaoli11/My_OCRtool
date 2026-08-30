from pathlib import Path
import sys
import winreg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autostart import RUN_KEY, VALUE_NAME, is_autostart_enabled, set_autostart


def read_original():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None


def restore_original(original) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if original is None:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        else:
            value, value_type = original
            winreg.SetValueEx(key, VALUE_NAME, 0, value_type, value)


def main() -> None:
    original = read_original()
    try:
        set_autostart(True)
        assert is_autostart_enabled(), "开启开机自启后未读到启动项"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            command, _ = winreg.QueryValueEx(key, VALUE_NAME)
        assert "--background" in command, "开机启动命令没有后台参数"

        set_autostart(False)
        assert not is_autostart_enabled(), "关闭开机自启后启动项仍存在"
    finally:
        restore_original(original)

    assert read_original() == original, "测试后未恢复原始开机启动项"
    print("Autostart registry round-trip passed and original state restored")


if __name__ == "__main__":
    main()
