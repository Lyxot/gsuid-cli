from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFont

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = PACKAGE_ROOT / "assets"
FONT_PATH = ASSETS_ROOT / "public" / "fonts" / "yuanshen_origin.ttf"


def asset_path(*parts: str) -> Path:
    return ASSETS_ROOT.joinpath(*parts)


def open_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def image_from_bytes(content: bytes, size: tuple[int, int]) -> Image.Image | None:
    try:
        return Image.open(BytesIO(content)).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    except OSError:
        return None


def png_bytes(image: Image.Image, *, rgb: bool = False) -> bytes:
    output = BytesIO()
    (image.convert("RGB") if rgb else image).save(
        output,
        format="PNG",
        optimize=True,
        compress_level=9,
    )
    return output.getvalue()


@lru_cache(maxsize=64)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size=size)


def int_value(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def bool_value(value: object) -> bool:
    return bool(value)


def sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else []


def text_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
