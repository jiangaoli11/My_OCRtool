"""Windows 本地 OCR 封装。

截图仅在本机内存中处理，不会发送到网络。
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageOps
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream


@dataclass(frozen=True)
class OcrLanguage:
    tag: str
    name: str


def _friendly_language_name(tag: str, fallback: str) -> str:
    normalized = tag.lower()
    if normalized.startswith("zh-hans"):
        return "简体中文"
    if normalized.startswith("zh-hant"):
        return "繁體中文"
    if normalized.startswith("en"):
        return "English"
    if normalized.startswith("ja"):
        return "日本語"
    if normalized.startswith("ko"):
        return "한국어"
    return fallback or tag


def available_languages() -> list[OcrLanguage]:
    """返回 Windows 当前已经安装的 OCR 语言。"""

    languages: list[OcrLanguage] = []
    for language in OcrEngine.available_recognizer_languages:
        languages.append(
            OcrLanguage(
                tag=language.language_tag,
                name=_friendly_language_name(
                    language.language_tag,
                    language.display_name,
                ),
            )
        )
    return languages


def _prepare_image(image: Image.Image, enhance_small_text: bool) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size

    if enhance_small_text and max(width, height) < 1800:
        scale = min(2.0, OcrEngine.max_image_dimension / max(width, height))
        if scale > 1.05:
            image = image.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )
            image = ImageEnhance.Contrast(image).enhance(1.08)

    width, height = image.size
    longest = max(width, height)
    if longest > OcrEngine.max_image_dimension:
        scale = OcrEngine.max_image_dimension / longest
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
    return image


async def _image_to_software_bitmap(image: Image.Image):
    png_bytes = io.BytesIO()
    image.save(png_bytes, format="PNG")

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png_bytes.getvalue())
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    return await decoder.get_software_bitmap_async()


async def _recognize_async(
    image: Image.Image,
    language_tag: str | None,
    enhance_small_text: bool,
) -> str:
    if language_tag:
        language = Language(language_tag)
        engine = OcrEngine.try_create_from_language(language)
        if engine is None:
            raise RuntimeError(f"Windows 未安装 {language_tag} 的 OCR 语言包。")
    else:
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            installed = available_languages()
            if not installed:
                raise RuntimeError("Windows 中没有可用的 OCR 语言包。")
            engine = OcrEngine.try_create_from_language(Language(installed[0].tag))

    prepared = _prepare_image(image, enhance_small_text)
    bitmap = await _image_to_software_bitmap(prepared)
    result = await engine.recognize_async(bitmap)

    lines = [line.text.strip() for line in result.lines if line.text.strip()]
    return "\n".join(lines).strip()


def recognize_image(
    image: Image.Image,
    language_tag: str | None = None,
    enhance_small_text: bool = True,
) -> str:
    """同步识别 PIL 图片，适合在工作线程中调用。"""

    return asyncio.run(_recognize_async(image, language_tag, enhance_small_text))
