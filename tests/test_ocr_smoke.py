from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_engine import available_languages, recognize_image


def main() -> None:
    languages = available_languages()
    assert languages, "Windows 没有安装 OCR 语言包"
    print("OCR languages:", ", ".join(item.tag for item in languages))

    canvas = Image.new("RGB", (1000, 250), "white")
    draw = ImageDraw.Draw(canvas)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = ImageFont.truetype(str(font_path), 78)
    draw.text((45, 65), "截图 OCR 测试 2026", fill="black", font=font)

    language = next((item.tag for item in languages if item.tag.lower().startswith("zh-hans")), None)
    # 与 GUI 的真实执行方式一致：在后台线程调用 WinRT OCR。
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(
            recognize_image,
            canvas,
            language,
            False,
        ).result(timeout=30)
    print("OCR result:", repr(result))
    assert result.strip(), "OCR 返回了空结果"
    assert "2026" in result.replace(" ", ""), "OCR 未识别出测试数字 2026"
    print("Smoke test passed")


if __name__ == "__main__":
    main()
