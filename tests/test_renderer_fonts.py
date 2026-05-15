from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from gsuid_cli.renderers.common import FALLBACK_FONT_PATH, FONT_PATH, font


def test_renderer_font_uses_subset_fallback_for_missing_glyph() -> None:
    primary = ImageFont.truetype(str(FONT_PATH), size=32)
    fallback = ImageFont.truetype(str(FALLBACK_FONT_PATH), size=32)

    assert primary.getmask("雺", "L").getbbox() is None
    assert fallback.getmask("雺", "L").getbbox() is not None

    image = Image.new("L", (160, 80), 0)
    draw = ImageDraw.Draw(image)
    draw.text((80, 40), "行雺", fill=255, font=font(32), anchor="mm")

    assert image.getbbox() is not None
