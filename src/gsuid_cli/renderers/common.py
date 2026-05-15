from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from io import BytesIO
from math import ceil, floor
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = PACKAGE_ROOT / "assets"
FONT_PATH = ASSETS_ROOT / "public" / "fonts" / "HYWenHei-65W.ttf"
FALLBACK_FONT_PATH = ASSETS_ROOT / "public" / "fonts" / "HYWenHei-55S-fallback.ttf"


def asset_path(*parts: str) -> Path:
    return ASSETS_ROOT.joinpath(*parts)


def open_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def v4_background(width: int, height: int, *, black_value: int = 190) -> Image.Image:
    source = Image.open(asset_path("public", "textures", "bg.jpg"))
    background = crop_center(source, width, height)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, black_value))
    background = background.filter(ImageFilter.GaussianBlur(radius=15)).convert("RGBA")
    background.paste(overlay, (0, 0), overlay)
    return background


def crop_center(image: Image.Image, width: int, height: int) -> Image.Image:
    source_width, source_height = image.size
    if source_width / source_height > width / height:
        resized_width = round(height * source_width / source_height)
        resized = image.resize((resized_width, height), Image.Resampling.LANCZOS)
        left = (resized_width - width) // 2
        return resized.crop((left, 0, left + width, height))
    resized_height = round(width * source_height / source_width)
    resized = image.resize((width, resized_height), Image.Resampling.LANCZOS)
    top = (resized_height - height) // 2
    return resized.crop((0, top, width, top + height))


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


class FallbackFont(ImageFont.ImageFont):
    def __init__(
        self,
        primary: ImageFont.FreeTypeFont,
        fallback: ImageFont.FreeTypeFont | None,
    ) -> None:
        super().__init__()
        self.primary = primary
        self.fallback = fallback
        self.size = primary.size

    def getmetrics(self) -> tuple[int, int]:
        return self.primary.getmetrics()

    def font_variant(self, *, size: float | None = None, **_: Any) -> FallbackFont:
        return font(int(size or self.size))

    def getlength(
        self,
        text: str | bytes,
        mode: str = "",
        direction: str | None = None,
        features: list[str] | None = None,
        language: str | None = None,
    ) -> float:
        if not isinstance(text, str) or not self._needs_fallback(text):
            return self.primary.getlength(text, mode, direction, features, language)
        return sum(
            run_font.getlength(run_text, mode, direction, features, language)
            for _, run_text, run_font in self._runs(
                text,
                mode,
                direction,
                features,
                language,
            )
        )

    def getbbox(
        self,
        text: str | bytes,
        mode: str = "",
        direction: str | None = None,
        features: list[str] | None = None,
        language: str | None = None,
        stroke_width: float = 0,
        anchor: str | None = None,
    ) -> tuple[float, float, float, float]:
        if not isinstance(text, str) or not self._needs_fallback(text):
            return self.primary.getbbox(
                text,
                mode,
                direction,
                features,
                language,
                stroke_width,
                anchor,
            )
        left, top, right, bottom = self._layout_bbox(
            text,
            mode,
            direction,
            features,
            language,
            stroke_width,
        )
        shift_x, shift_y = self._anchor_shift(
            text,
            mode,
            direction,
            features,
            language,
            stroke_width,
            anchor,
        )
        return left + shift_x, top + shift_y, right + shift_x, bottom + shift_y

    def getmask(self, text: str | bytes, mode: str = "", *args: Any, **kwargs: Any) -> Any:
        return self.getmask2(text, mode, *args, **kwargs)[0]

    def getmask2(
        self,
        text: str | bytes,
        mode: str = "",
        direction: str | None = None,
        features: list[str] | None = None,
        language: str | None = None,
        stroke_width: float = 0,
        anchor: str | None = None,
        ink: int = 0,
        start: tuple[float, float] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, tuple[int, int]]:
        if not isinstance(text, str) or not self._needs_fallback(text):
            return self.primary.getmask2(
                text,
                mode,
                direction,
                features,
                language,
                stroke_width,
                anchor,
                ink,
                start,
                *args,
                **kwargs,
            )

        left, top, right, bottom = self._layout_bbox(
            text,
            mode,
            direction,
            features,
            language,
            stroke_width,
        )
        shift_x, shift_y = self._anchor_shift(
            text,
            mode,
            direction,
            features,
            language,
            stroke_width,
            anchor,
        )
        mask_left = floor(left)
        mask_top = floor(top)
        width = max(0, ceil(right) - mask_left)
        height = max(0, ceil(bottom) - mask_top)
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        for x, run_text, run_font in self._runs(
            text,
            mode,
            direction,
            features,
            language,
        ):
            draw.text(
                (x - mask_left, -mask_top),
                run_text,
                fill=255,
                font=run_font,
                anchor="la",
                stroke_width=stroke_width,
                stroke_fill=255,
            )
        return mask.im, (mask_left + floor(shift_x), mask_top + floor(shift_y))

    def _needs_fallback(self, text: str) -> bool:
        return self.fallback is not None and any(
            self._font_for_char(char) is self.fallback for char in text
        )

    def _font_for_char(self, char: str) -> ImageFont.FreeTypeFont:
        if self.fallback is None:
            return self.primary
        if _font_renders(self.primary, char):
            return self.primary
        if _font_renders(self.fallback, char):
            return self.fallback
        return self.primary

    def _runs(
        self,
        text: str,
        mode: str,
        direction: str | None,
        features: list[str] | None,
        language: str | None,
    ) -> list[tuple[float, str, ImageFont.FreeTypeFont]]:
        runs: list[tuple[float, str, ImageFont.FreeTypeFont]] = []
        cursor = 0.0
        current_text = ""
        current_font: ImageFont.FreeTypeFont | None = None
        current_x = 0.0
        for char in text:
            run_font = self._font_for_char(char)
            if current_text and run_font is not current_font:
                assert current_font is not None
                runs.append((current_x, current_text, current_font))
                cursor += current_font.getlength(current_text, mode, direction, features, language)
                current_x = cursor
                current_text = ""
            current_text += char
            current_font = run_font
        if current_text and current_font is not None:
            runs.append((current_x, current_text, current_font))
        return runs

    def _layout_bbox(
        self,
        text: str,
        mode: str,
        direction: str | None,
        features: list[str] | None,
        language: str | None,
        stroke_width: float,
    ) -> tuple[float, float, float, float]:
        left = top = right = bottom = None
        for x, run_text, run_font in self._runs(
            text,
            mode,
            direction,
            features,
            language,
        ):
            run_left, run_top, run_right, run_bottom = run_font.getbbox(
                run_text,
                mode,
                direction,
                features,
                language,
                stroke_width,
                "la",
            )
            left = x + run_left if left is None else min(left, x + run_left)
            top = run_top if top is None else min(top, run_top)
            right = x + run_right if right is None else max(right, x + run_right)
            bottom = run_bottom if bottom is None else max(bottom, run_bottom)
        if left is None or top is None or right is None or bottom is None:
            return 0, 0, 0, 0
        return left, top, right, bottom

    def _anchor_shift(
        self,
        text: str,
        mode: str,
        direction: str | None,
        features: list[str] | None,
        language: str | None,
        stroke_width: float,
        anchor: str | None,
    ) -> tuple[float, float]:
        if anchor in (None, "la"):
            return 0, 0
        base = self.primary.getbbox(
            text,
            mode,
            direction,
            features,
            language,
            stroke_width,
            "la",
        )
        anchored = self.primary.getbbox(
            text,
            mode,
            direction,
            features,
            language,
            stroke_width,
            anchor,
        )
        return anchored[0] - base[0], anchored[1] - base[1]


@lru_cache(maxsize=64)
def _primary_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size=size)


@lru_cache(maxsize=64)
def _fallback_font(size: int) -> ImageFont.FreeTypeFont | None:
    if not FALLBACK_FONT_PATH.exists():
        return None
    return ImageFont.truetype(str(FALLBACK_FONT_PATH), size=size)


@lru_cache(maxsize=8192)
def _font_renders(text_font: ImageFont.FreeTypeFont, char: str) -> bool:
    return text_font.getmask(char, "L").getbbox() is not None


@lru_cache(maxsize=64)
def font(size: int) -> FallbackFont:
    return FallbackFont(_primary_font(size), _fallback_font(size))


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
