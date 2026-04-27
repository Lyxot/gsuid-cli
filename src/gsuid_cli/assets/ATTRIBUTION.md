# Asset Attribution

Some renderer assets are copied or adapted from
KimigaiiWuyi/GenshinUID (GPL-3.0,
`https://github.com/KimigaiiWuyi/GenshinUID`) for GenshinUID-parity image
rendering.

- Daily note textures, daily materials textures, player character-list
  textures, player summary/exploration textures, player inventory textures,
  player calendar textures, player diary textures, challenge textures, progress
  textures, shared title/footer/mask textures, the shared v4 background, weapon
  rarity backgrounds, character-card frame/background textures, and the bundled
  Yuanshen font are from GenshinUID historical renderer assets.
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
- Challenge Abyss textures are copied from
  `GenshinUID/genshinuid_abyss/texture2D/`.
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
- Progress collection/exploration slider and base-mask textures are copied from
  `GenshinUID/utils/resource/texture2d/`; the collection/exploration/GCG-deck
  background is copied from `GenshinUID/utils/image/bg/nm_bg/zy.jpg`.
- Wiki PicWiki textures are copied from
  `GenshinUID/genshinuid_wikitext/texture2D/`; wiki star and unknown-icon
  textures are copied from `GenshinUID/utils/resource/texture2d/weapon_star/`
  and `GenshinUID/utils/image/texture2d/`.
- Player character portraits, weapon icons, and namecard backgrounds are
  fetched from the GenshinUID resource mirror under
  `https://example.test/GenshinUID/resource/`.
- Character guide images and reference-panel images are fetched from the
  GenshinUID resource mirror under
  `https://example.test/GenshinUID/wiki/`.
- Build and holder recommendation data is fetched from GenshinUID
  `GenshinUID/genshinuid_adv/char_adv_list.json`.
- Abyss guide schedule and monster data is bundled from GenshinUID
  `GenshinUID/genshinuid_guide/abyss.js`, where the rendered data credit is
  `妮可少年`; theater guide data is fetched from the Hakush rolecombat API used by GenshinUID.
- The CLI renderer code that uses these assets is adapted for this
  repository's command contract and static asset cache.
