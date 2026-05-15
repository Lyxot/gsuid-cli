# Asset Attribution

Some renderer assets are copied or adapted from
KimigaiiWuyi/GenshinUID (GPL-3.0,
`https://github.com/KimigaiiWuyi/GenshinUID`) for GenshinUID-parity image
rendering.

- Daily note textures, daily materials textures, player character-list
  textures, player summary/exploration textures, player inventory textures,
  player calendar textures, player diary textures, event-list textures,
  announcement-list textures, gacha summary textures, panel textures, rank
  textures, challenge textures, progress textures, shared title/footer/mask
  textures, the shared v4 background, weapon rarity backgrounds,
  character-card frame/background textures.
- Player character-list textures are copied from
  `GenshinUID/genshinuid_roleinfo/texture2d/`; the shared v4 background is
  copied from `GenshinUID/utils/image/texture2d/bg.jpg`.
- Player summary/exploration textures are copied from
  `GenshinUID/genshinuid_collection/texture2D/`; title/footer/mask textures are
  copied from `GenshinUID/utils/image/texture2d/`.
- Player inventory textures are copied from
  `GenshinUID/genshinuid_compute/texture2d/`.
- Player calendar textures are copied from
  `GenshinUID/genshinuid_cale/texture2d/`.
- Player diary textures are copied from
  `GenshinUID/genshinuid_note/texture2d/`, with the diary background and avatar
  ring assets copied from `GenshinUID/utils/image/`.
- Event-list textures are copied from
  `GenshinUID/genshinuid_eventlist/texture2d/`.
- Announcement-list textures are copied from
  `GenshinUID/genshinuid_ann/assets/`.
- Gacha summary textures and emotion icons are copied from
  `GenshinUID/genshinuid_gachalog/texture2d/`; character name/id maps are
  copied from `GenshinUID/utils/map/data/`.
- Panel textures are copied from `GenshinUID/genshinuid_enka/texture2D/` and
  `GenshinUID/utils/resource/texture2d/weapon_affix/`; compact panel text-map
  JSON files are copied from `GenshinUID/utils/map/data/`; reference scoring
  and damage-table JSON files are copied from `GenshinUID/genshinuid_enka/effect/`.
- Panel graduation textures are copied from `GenshinUID/genshinuid_count/texture2d/`
  and shared count/fetter badge textures are copied from
  `GenshinUID/genshinuid_enka/count_texture2d/` and
  `GenshinUID/utils/resource/texture2d/fetter/`.
- Rank textures are copied from `GenshinUID/genshinuid_enka/rank_texture2d/`,
  `GenshinUID/genshinuid_enka/count_texture2d/`, and
  `GenshinUID/genshinuid_enka/texture2D/rank_img/`; rank badge textures are
  copied from `GenshinUID/utils/resource/texture2d/talent/`.
- Rerun-list textures are copied from `GenshinUID/genshinuid_returnlist/texture2d/`.
- Primogem-plan static images are copied from
  `GenshinUID/genshinuid_etcimg/primogems_data/`.
- Challenge Abyss textures are copied from
  `GenshinUID/genshinuid_abyss/texture2D/`; the Abyss card background is copied
  from `GenshinUID/utils/image/bg/nm_bg/zy.jpg`.
- Challenge Theater textures are copied from
  `GenshinUID/genshinuid_poetry_abyss/texture2d/`.
- Challenge hard-mode textures are copied from
  `GenshinUID/genshinuid_hard_challenge/texture2d/`.
- Guide Abyss textures are copied from
  `GenshinUID/genshinuid_guide/texture2d/`; the title icon is copied from
  `GenshinUID/utils/resource/texture2d/icon.png`.
- Guide Theater textures are copied from
  `GenshinUID/genshinuid_guide/texture2d2/`.
- Shared avatar ring and character-card textures are copied from
  `GenshinUID/utils/image/texture2d/` and
  `GenshinUID/utils/resource/texture2d/char_card/`.
- Progress achievement textures are copied from
  `GenshinUID/genshinuid_achievement/texture2d/`.
- Progress GCG textures are copied from `GenshinUID/genshinuid_gcg/texture2d/`.
- Progress GCG card-name lookup data is derived from the Simplified Chinese
  GCG list served by the AMBR/Yatta API (`https://gi.yatta.moe/api/v2/chs/gcg`).
- Progress collection/exploration slider and base-mask textures are copied from
  `GenshinUID/utils/resource/texture2d/`; the collection/exploration/GCG-deck
  background is copied from `GenshinUID/utils/image/bg/nm_bg/zy.jpg`.
- Wiki PicWiki textures are copied from
  `GenshinUID/genshinuid_wikitext/texture2D/`; wiki star and unknown-icon
  textures are copied from `GenshinUID/utils/resource/texture2d/weapon_star/`
  and `GenshinUID/utils/image/texture2d/`.
- Player character portraits, weapon icons, and namecard backgrounds are
  fetched from the GenshinUID resource mirror under
  `genshinuid://resource/`.
- Character guide images and reference-panel images are fetched from the
  GenshinUID resource mirror under
  `genshinuid://wiki/`.
- Build and holder recommendation data is fetched from GenshinUID
  `GenshinUID/genshinuid_adv/char_adv_list.json`.
- Abyss guide schedule and monster data is fetched from GenshinUID
  `GenshinUID/genshinuid_guide/abyss.js` by resolving the latest commit for
  that path on the default branch history and then using jsDelivr, where the
  rendered data credit is `妮可少年`; theater guide data is fetched from the Hakush rolecombat API used by GenshinUID.
- Achievement and commission guide lookup data is fetched from GenshinUID
  `GenshinUID/genshinuid_achievement/all_achi.json` and
  `GenshinUID/genshinuid_achievement/daily_achi.json`.
- The CLI renderer code that uses these assets is adapted for this
  repository's command contract and static asset cache.
