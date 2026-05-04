# Command Reference

Generated from `gsuid meta capabilities`.

| Command | Auth | Render | Cache | Description |
| --- | --- | --- | --- | --- |
| `account.add` | `none` | `data` | `off` | Add or update a local account. |
| `account.default` | `none` | `data` | `off` | Set the default account for the selected profile. |
| `account.list` | `none` | `data` | `off` | List local accounts. |
| `account.remove` | `none` | `data` | `off` | Remove a local account. |
| `account.show` | `none` | `data` | `off` | Show one local account. |
| `announcements.list` | `none` | `data, image, text, all` | `use` | List public game announcement rows. |
| `announcements.show` | `none` | `data, image, text, all` | `use` | Show one public game announcement row. |
| `auth.cookie.delete` | `keyring` | `data` | `off` | Delete a stored cookie from the OS keyring. |
| `auth.cookie.set` | `keyring` | `data` | `off` | Store a cookie in the OS keyring. |
| `auth.cookie.test` | `cookie` | `data` | `off` | Validate cookie availability against the CN provider. |
| `auth.device.delete` | `none` | `data` | `off` | Delete local MYS device metadata. |
| `auth.device.set` | `cookie` | `data` | `off` | Bind and store MYS device metadata for account requests. |
| `auth.device.test` | `device` | `data` | `off` | Check local MYS device metadata availability. |
| `auth.gacha-url.delete` | `keyring` | `data` | `off` | Delete a stored gacha authkey URL from the OS keyring. |
| `auth.gacha-url.set` | `keyring` | `data` | `off` | Store a gacha authkey URL in the OS keyring. |
| `auth.gacha-url.test` | `gacha_url` | `data` | `off` | Check local gacha URL availability without provider validation. |
| `auth.qrcode.complete` | `keyring` | `data` | `off` | Complete a confirmed QR login and store credentials. |
| `auth.qrcode.login` | `keyring` | `data` | `off` | Run interactive QR login and store credentials. |
| `auth.qrcode.poll` | `none` | `data` | `off` | Poll a QR login session once. |
| `auth.qrcode.start` | `none` | `data` | `off` | Create a QR login session. |
| `auth.stoken.delete` | `keyring` | `data` | `off` | Delete a stored stoken from the OS keyring. |
| `auth.stoken.set` | `keyring` | `data` | `off` | Store a stoken in the OS keyring. |
| `auth.stoken.test` | `stoken` | `data` | `off` | Check local stoken availability without provider validation. |
| `batch.plan` | `none` | `data` | `off` | Validate JSONL batch commands without executing them. |
| `batch.run` | `mixed` | `data` | `mixed` | Execute JSONL batch commands and return nested envelopes. |
| `cache.clear` | `none` | `data` | `off` | Clear local cache and artifact files by scope. |
| `challenge.abyss` | `cookie` | `data, image, text, all` | `off` | Show authenticated Spiral Abyss data. |
| `challenge.hard` | `cookie` | `data, image, text, all` | `off` | Show authenticated Stygian Onslaught hard challenge data. |
| `challenge.hard-rank` | `none` | `data, text, all` | `off` | Report hard challenge ranking support status. |
| `challenge.theater` | `cookie` | `data, image, text, all` | `off` | Show authenticated Imaginarium Theater data. |
| `codes.list` | `none` | `data, text, all` | `use` | List public active redeem-code rows. |
| `daily.bbs-coin` | `none` | `data, text, all` | `off` | Report BBS coin task support status. |
| `daily.materials` | `none` | `data, image, text, all` | `use` | List daily talent and weapon material domains. |
| `daily.note` | `cookie` | `data, image, text, all` | `off` | Show current resin, commissions, expeditions, and teapot status. |
| `daily.signin` | `cookie` | `data, text, all` | `off` | Claim or report the MYS daily sign-in status. |
| `events.banners` | `none` | `data, image, text, all` | `use` | List public event banner artwork URLs. |
| `events.list` | `none` | `data, image, text, all` | `use` | List public event announcements. |
| `gacha.authkey` | `gacha_url` | `data` | `off` | Show stored gacha authkey URL availability without revealing it. |
| `gacha.authkey.refresh` | `cookie+stoken` | `data` | `off` | Generate and store a gacha authkey URL from cookie and stoken. |
| `gacha.export` | `none` | `data` | `off` | Export local gacha logs as UIGF JSON. |
| `gacha.import` | `none` | `data` | `off` | Import UIGF JSON into local gacha storage. |
| `gacha.refresh` | `gacha_url` | `data` | `off` | Refresh local gacha logs from a stored authkey URL. |
| `gacha.summary` | `none` | `data, image, all` | `off` | Summarize local gacha logs. |
| `guide.abyss` | `none` | `data, image, text, all` | `use` | Show public abyss guide data and GenshinUID-style monster layout. |
| `guide.character` | `none` | `data, image, all` | `use` | Show public character guide facts and GenshinUID guide image. |
| `guide.reference-panel` | `none` | `data, image, all` | `use` | Show the GenshinUID reference-panel image for a character. |
| `guide.route` | `none` | `data, image, all` | `use` | Fetch a public material route map artifact. |
| `guide.theater` | `none` | `data, image, text, all` | `use` | Show public theater guide data and GenshinUID-style monster layout. |
| `map.find` | `none` | `data, image, all` | `use` | Fetch a public MiniGG material map artifact. |
| `meta.capabilities` | `none` | `data` | `off` | Show implemented command capabilities. |
| `meta.doctor` | `none` | `data` | `off` | Run local diagnostics for storage, credentials, resources, or network. |
| `meta.errors` | `none` | `data` | `off` | Show stable machine-readable error metadata. |
| `meta.paths` | `none` | `data` | `off` | Show resolved local storage paths. |
| `meta.schema` | `none` | `data` | `off` | Show JSON envelope schema metadata. |
| `meta.version` | `none` | `data` | `off` | Show package, Python, and git version metadata. |
| `misc.primogems-plan` | `none` | `data, image, all` | `use` | Show the GenshinUID static version-plan primogem image. |
| `monitor.once` | `none` | `data` | `off` | Run one local health check pass with caller thresholds. |
| `panel.artifacts` | `none` | `data, image, all` | `off` | List cached artifacts for a UID. |
| `panel.compare` | `none` | `data, image, all` | `off` | Compare cached panel stats for two or more builds. |
| `panel.graduation` | `none` | `data, image, all` | `off` | Summarize local cached graduation inputs and render GenshinUID-style rows. |
| `panel.list` | `none` | `data` | `off` | List cached character panels for a UID. |
| `panel.refresh` | `none` | `data` | `use` | Refresh Enka showcase panel data into the local cache. |
| `panel.save` | `none` | `data` | `off` | Save one cached panel as a JSON artifact. |
| `panel.show` | `none` | `data, image, all` | `off` | Show one cached character panel. |
| `panel.showcase` | `none` | `data, image, all` | `off` | Show the cached public showcase summary. |
| `player.calendar` | `cookie` | `data, image, text, all` | `off` | Show authenticated player activity calendar data. |
| `player.characters` | `cookie` | `data, image, text, all` | `off` | Show authenticated player character details. |
| `player.diary` | `cookie` | `data, image, text, all` | `off` | Show authenticated monthly traveler diary data. |
| `player.inventory` | `cookie` | `data, image, text, all` | `off` | Show owned-character and equipped-weapon material counts. Coverage: `owned_character_ascension_and_equipped_weapon_materials`. |
| `player.register-time` | `cookie` | `data, text, all` | `off` | Attempt to show Genshin account registration time. Availability: `upstream-limited`. Limitations: Uses the legacy MYS anniversary endpoint, which may return provider retcode -502. |
| `player.summary` | `cookie` | `data, image, text, all` | `off` | Show authenticated player profile summary data. |
| `profile.default` | `none` | `data` | `off` | Set the default local profile. |
| `profile.delete` | `none` | `data` | `off` | Delete a local profile. |
| `profile.init` | `none` | `data` | `off` | Create or update a local profile. |
| `profile.list` | `none` | `data` | `off` | List local profiles. |
| `profile.show` | `none` | `data` | `off` | Show one local profile. |
| `progress.achievement-guide` | `none` | `data` | `off` | Report achievement guide lookup support status. |
| `progress.achievements` | `cookie` | `data, image, all` | `off` | Show authenticated achievement category data. |
| `progress.collection` | `cookie` | `data, image, all` | `off` | Show authenticated collection count data. |
| `progress.commission-guide` | `none` | `data` | `off` | Report commission guide lookup support status. |
| `progress.completion` | `cookie` | `data, image, all` | `off` | Show authenticated account completion summary data. |
| `progress.exploration` | `cookie` | `data, image, all` | `off` | Show authenticated world exploration data. |
| `progress.gcg` | `cookie` | `data, image, all` | `off` | Show authenticated Genius Invokation TCG data. |
| `progress.gcg-deck` | `cookie` | `data, image, all` | `off` | Show authenticated Genius Invokation TCG deck data. |
| `rank.artifact` | `none` | `data, image, all` | `off` | Show the Akasha global artifact leaderboard. |
| `rank.character` | `none` | `data, image, all` | `off` | Show a character Akasha leaderboard or nearby UID rank rows. |
| `rank.list` | `none` | `data, image, all` | `off` | Render a UID's Akasha rank list. |
| `recommend.build` | `none` | `data, image, text, all` | `use` | Show GenshinUID character build recommendations. |
| `recommend.holder` | `none` | `data, image, text, all` | `use` | Show GenshinUID holder recommendations for a weapon or artifact. |
| `rerun.list` | `none` | `data, image, text, all` | `use` | List rerun rows and render the GenshinUID return list. |
| `resources.sync` | `none` | `data` | `memory` | Fetch public resource metadata and warm process-local JSON cache. |
| `wiki.artifact` | `none` | `data, image, text, all` | `use` | Look up public artifact set data. |
| `wiki.character` | `none` | `data, text, all` | `use` | Look up public character data. |
| `wiki.character-materials` | `none` | `data, image, text, all` | `use` | Show public character material data. |
| `wiki.constellation` | `none` | `data, image, text, all` | `use` | Look up public character constellation data. |
| `wiki.enemy` | `none` | `data, text, all` | `use` | Look up public enemy data. |
| `wiki.food` | `none` | `data, image, text, all` | `use` | Look up public food data. |
| `wiki.talent` | `none` | `data, text, all` | `use` | Look up public character talent data. |
| `wiki.weapon` | `none` | `data, image, text, all` | `use` | Look up public weapon data. |
| `wiki.weapon-materials` | `none` | `data, image, text, all` | `use` | Show public weapon material data. |

Notes:

- JSON mode is the stable machine contract.
- `--render data` includes `data` and `sources`; artifact-only renders keep stdout compact.
- `--debug` writes a redacted debug artifact.
- `auth` describes required credential type, not whether a command can fail upstream.
- `render` lists supported result modes; artifacts are returned by absolute path.
- Stage 17 is porting GenshinUID-parity renderers group by group; `meta capabilities` is the source of truth for current image support.
- `cache` describes intended command cache behavior.
