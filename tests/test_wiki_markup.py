from __future__ import annotations

import pytest

from gsuid_cli.renderers.wiki.picwiki import (
    render_wiki_artifact_card,
    render_wiki_constellation_card,
)
from gsuid_cli.renderers.wiki.text import (
    render_wiki_constellation_text,
    render_wiki_lookup_text,
)


@pytest.mark.parametrize("render", ["text", "image"])
def test_wiki_constellation_link_markup_matches_plain_output(render) -> None:
    plain = "递变信标的携带上限提升至5枚。\n施放律定·变量侦测时，额外创造一枚。"
    marked = (
        "{LINK#N11360001}递变信标{/LINK}的携带上限提升至5枚。\\n"
        "施放{link#S11362}律定·变量侦测{/link}时，额外创造一枚。"
    )

    def output(description):
        row = {"index": 1, "name": "变量", "description": description}
        if render == "text":
            return render_wiki_constellation_text({"character": "米提亚", "constellation": row})
        return render_wiki_constellation_card({"constellation": {"c1": row}}, constellation=1)

    expected = output(plain)
    if render == "text":
        assert plain in expected
    assert output(marked) == expected


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("render", ["text", "image"])
def test_wiki_artifact_effect_markup_matches_plain_output(count, render) -> None:
    plain = ["攻击力提高18%。", "施放战技时，伤害提高20%。"][:count]
    marked = [
        "<i>攻击力</i>提高<color=#FFD780FF>18%</color>。",
        "{LINK}施放战技{/LINK}时，伤害提高<color=#FFD780>20%</color>。",
    ][:count]

    def output(effects):
        item = {"name": "角斗士的终幕礼", "bonuses": dict(enumerate(effects))}
        if render == "text":
            return render_wiki_lookup_text("artifact", item)
        return render_wiki_artifact_card(item)

    expected = output(plain)
    if render == "text":
        for effect in plain:
            assert effect in expected
    assert output(marked) == expected
