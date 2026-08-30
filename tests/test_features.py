from pathlib import Path
import sys
import tempfile
import tkinter as tk

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ScreenshotOcrApp
from autostart import _launch_command
from screenshot_widgets import ImageEditor, PinWindow
from settings_store import AppSettings, SettingsStore


def test_settings_round_trip() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        store = SettingsStore()
        store.path = Path(temporary) / "settings.json"
        expected = AppSettings(
            close_action="tray",
            image_format="JPG",
            default_capture_action="edit",
            hotkey="Ctrl+Shift+S",
            autostart=True,
        )
        store.save(expected)
        actual = store.load()
        assert actual.close_action == "tray"
        assert actual.image_format == "JPG"
        assert actual.default_capture_action == "edit"
        assert actual.hotkey == "Ctrl+Shift+S"
        assert actual.autostart is True
    assert "--background" in _launch_command()


def test_widgets_and_tray() -> None:
    root = tk.Tk()
    root.withdraw()
    app = ScreenshotOcrApp(root)
    image = Image.new("RGB", (360, 180), "white")

    app.show_settings()
    root.update_idletasks()
    root.update()
    dialog = app.settings_dialog
    assert dialog is not None
    save_bottom = (
        dialog.save_button.winfo_rooty()
        + dialog.save_button.winfo_height()
        - dialog.window.winfo_rooty()
    )
    assert dialog.save_button.winfo_viewable(), "设置保存按钮不可见"
    assert save_bottom <= dialog.window.winfo_height(), "设置保存按钮超出窗口"
    dialog.window.destroy()

    applied: list[Image.Image] = []
    editor = ImageEditor(
        root,
        image,
        AppSettings().default_save_dir,
        "PNG",
        applied.append,
        lambda _image: None,
        lambda _image: None,
        lambda _text: None,
    )
    editor.window.withdraw()
    editor.rotate(90)
    editor.undo()
    editor.redo()
    editor.apply()
    assert applied and applied[0].size == (180, 360)

    pin = PinWindow(
        root,
        image,
        AppSettings().default_save_dir,
        "PNG",
        lambda _image: None,
        lambda _pin: None,
        lambda _text: None,
    )
    pin.window.withdraw()
    pin.close()

    app.hide_to_tray()
    root.update()
    root.after(900, app.exit_app)
    root.mainloop()
    assert app.is_quitting


def main() -> None:
    test_settings_round_trip()
    test_widgets_and_tray()
    print("Feature smoke tests passed")


if __name__ == "__main__":
    main()
