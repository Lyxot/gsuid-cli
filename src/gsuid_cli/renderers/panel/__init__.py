"""Panel renderers."""

from gsuid_cli.renderers.panel.image import (
    character_full_image_url,
    character_icon_url,
    panel_artifacts_asset_urls,
    panel_asset_urls,
    panel_graduation_asset_urls,
    panel_showcase_asset_urls,
    render_panel_artifacts_library,
    render_panel_compare_cards,
    render_panel_graduation,
    render_panel_show_card,
    render_panel_showcase,
)
from gsuid_cli.renderers.panel.metrics import artifact_effective_score, panel_reference_metrics
from gsuid_cli.renderers.panel.text import (
    render_panel_artifacts_text,
    render_panel_compare_text,
    render_panel_graduation_text,
    render_panel_list_text,
    render_panel_refresh_text,
    render_panel_save_text,
    render_panel_show_text,
    render_panel_showcase_text,
)

__all__ = [
    "artifact_effective_score",
    "character_full_image_url",
    "character_icon_url",
    "panel_artifacts_asset_urls",
    "panel_asset_urls",
    "panel_graduation_asset_urls",
    "panel_reference_metrics",
    "panel_showcase_asset_urls",
    "render_panel_artifacts_library",
    "render_panel_artifacts_text",
    "render_panel_compare_cards",
    "render_panel_compare_text",
    "render_panel_graduation",
    "render_panel_graduation_text",
    "render_panel_list_text",
    "render_panel_refresh_text",
    "render_panel_save_text",
    "render_panel_show_card",
    "render_panel_show_text",
    "render_panel_showcase",
    "render_panel_showcase_text",
]
