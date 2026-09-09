from gsuid_cli.renderers.player import summary
from gsuid_cli.renderers.progress import collection


def test_collection_maxima_match_genshinuid_7_0() -> None:
    assert set(collection.COLLECTION_MAX.values()) == {
        74,
        410,
        416,
        839,
        1073,
        1839,
        3372,
        3838,
    }
    assert set(summary.CHEST_MAX.values()) == {410, 416, 1073, 3372, 3838}

    for name, maximum in summary.CHEST_MAX.items():
        assert summary.CMAP[name] == [
            maximum,
            int(maximum * 4 / 5),
            int(maximum * 3 / 5),
            int(maximum * 2 / 5),
            int(maximum / 5),
        ]


def test_iceculus_uses_ice_icon_and_cryo_label() -> None:
    assert summary.STCMAP["ice"] == summary.STCMAP["cryo"]
    assert collection.STCMAP["ice"] == collection.STCMAP["cryo"]
    assert (summary.SUMMARY_TEXTURE / "Item_Iceculus.webp").is_file()

    bars = collection._exploration_bars({"stats": {"iceculus_number": 42}})
    assert bars[1][0] == collection.STCMAP["ice"]
    assert bars[1][1] == 42 / 271
