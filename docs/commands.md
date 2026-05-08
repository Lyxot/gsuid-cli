# Command Reference

Generated from `gsuid meta capabilities`.

| Command | Auth | Render | Description |
| --- | --- | --- | --- |
| `account.add` | `none` | `data, text, all` | Add or update a local account. |
| `account.default` | `none` | `data, text, all` | Set the default account for the selected profile. |
| `account.list` | `none` | `data, text, all` | List local accounts. |
| `account.remove` | `none` | `data, text, all` | Remove a local account. |
| `account.show` | `none` | `data, text, all` | Show one local account. |
| `announcements.list` | `none` | `data, image, text, all` | List public game announcement rows. |
| `announcements.show` | `none` | `data, image, text, all` | Show one public game announcement row. |
| `auth.cookie.delete` | `keyring` | `data, text, all` | Delete a stored cookie from the OS keyring. |
| `auth.cookie.set` | `keyring` | `data, text, all` | Store a cookie in the OS keyring. |
| `auth.cookie.test` | `cookie` | `data, text, all` | Validate cookie availability against the CN provider. |
| `auth.device.delete` | `none` | `data, text, all` | Delete local MYS device metadata. |
| `auth.device.set` | `cookie` | `data, text, all` | Bind and store MYS device metadata for account requests. |
| `auth.device.test` | `device` | `data, text, all` | Check local MYS device metadata availability. |
| `auth.gacha-url.delete` | `keyring` | `data, text, all` | Delete a stored gacha authkey URL from the OS keyring. |
| `auth.gacha-url.set` | `keyring` | `data, text, all` | Store a gacha authkey URL in the OS keyring. |
| `auth.gacha-url.test` | `gacha_url` | `data, text, all` | Check local gacha URL availability without provider validation. |
| `auth.qrcode.complete` | `keyring` | `data, text, all` | Complete a confirmed QR login and store credentials. |
| `auth.qrcode.login` | `keyring` | `data, image, text, all` | Run interactive QR login and store credentials. |
| `auth.qrcode.poll` | `none` | `data, text, all` | Poll a QR login session once. |
| `auth.qrcode.start` | `none` | `data, image, text, all` | Create a QR login session. |
| `auth.stoken.delete` | `keyring` | `data, text, all` | Delete a stored stoken from the OS keyring. |
| `auth.stoken.set` | `keyring` | `data, text, all` | Store a stoken in the OS keyring. |
| `auth.stoken.test` | `stoken` | `data, text, all` | Check local stoken availability without provider validation. |
| `batch.plan` | `none` | `data, text, all` | Validate JSONL batch commands without executing them. |
| `batch.run` | `mixed` | `data, text, all` | Execute JSONL batch commands and return nested envelopes. |
| `cache.clear` | `none` | `data, text, all` | Clear local cache and artifact files by scope. |
| `cache.size` | `none` | `data, text, all` | Show local cache and artifact disk usage by scope. |
| `challenge.abyss` | `cookie` | `data, image, text, all` | Show authenticated Spiral Abyss data. |
| `challenge.hard` | `cookie` | `data, image, text, all` | Show authenticated Stygian Onslaught hard challenge data. |
| `challenge.hard-rank` | `none` | `data, text, all` | Show the Akasha Stygian Onslaught ranking. |
| `challenge.theater` | `cookie` | `data, image, text, all` | Show authenticated Imaginarium Theater data. |
| `codes.list` | `none` | `data, text, all` | List public active redeem-code rows. |
| `daily.bbs-coin` | `stoken` | `data, text, all` | Run and report MYS BBS coin tasks. |
| `daily.materials` | `none` | `data, image, text, all` | List daily talent and weapon material domains. |
| `daily.note` | `cookie` | `data, image, text, all` | Show current resin, commissions, expeditions, and teapot status. |
| `daily.signin` | `cookie` | `data, text, all` | Claim or report the MYS daily sign-in status. |
| `events.banners` | `none` | `data, image, text, all` | List public event banner artwork URLs. |
| `events.list` | `none` | `data, image, text, all` | List public event announcements. |
| `gacha.authkey` | `gacha_url` | `data, text, all` | Show stored gacha authkey URL availability without revealing it. |
| `gacha.authkey.refresh` | `cookie+stoken` | `data, text, all` | Generate and store a gacha authkey URL from cookie and stoken. |
| `gacha.export` | `none` | `data, text, all` | Export local gacha logs as UIGF JSON. |
| `gacha.import` | `none` | `data, text, all` | Import UIGF JSON into local gacha storage. |
| `gacha.refresh` | `gacha_url` | `data, text, all` | Refresh local gacha logs from a stored authkey URL. |
| `gacha.summary` | `none` | `data, image, text, all` | Summarize local gacha logs. |
| `guide.abyss` | `none` | `data, image, text, all` | Show public abyss guide data and GenshinUID-style monster layout. |
| `guide.character` | `none` | `data, image, all` | Show public character guide facts and GenshinUID guide image. |
| `guide.reference-panel` | `none` | `data, image, all` | Show the GenshinUID reference-panel image for a character. |
| `guide.route` | `none` | `data, image, all` | Fetch a public material route map artifact. |
| `guide.theater` | `none` | `data, image, text, all` | Show public theater guide data and GenshinUID-style monster layout. |
| `map.find` | `none` | `data, image, all` | Fetch a public MiniGG material map artifact. |
| `meta.capabilities` | `none` | `data, text, all` | Show implemented command capabilities. |
| `meta.doctor` | `none` | `data, text, all` | Run local diagnostics for storage, credentials, resources, or network. |
| `meta.errors` | `none` | `data, text, all` | Show stable machine-readable error metadata. |
| `meta.paths` | `none` | `data, text, all` | Show resolved local storage paths. |
| `meta.schema` | `none` | `data, text, all` | Show JSON envelope schema metadata. |
| `meta.version` | `none` | `data, text, all` | Show package, Python, and git version metadata. |
| `misc.primogems-plan` | `none` | `data, image, all` | Show the GenshinUID static version-plan primogem image. |
| `monitor.once` | `none` | `data, text, all` | Run one local health check pass with caller thresholds. |
| `panel.artifacts` | `none` | `data, image, text, all` | List cached artifacts for a UID. |
| `panel.compare` | `none` | `data, image, text, all` | Compare cached panel stats for two or more builds. |
| `panel.graduation` | `none` | `data, image, text, all` | Summarize local cached graduation inputs and render GenshinUID-style rows. |
| `panel.list` | `none` | `data, text, all` | List cached character panels for a UID. |
| `panel.refresh` | `none` | `data, text, all` | Refresh Enka showcase or MYS character detail panel data into the local cache. |
| `panel.save` | `none` | `data, text, all` | Save one cached panel as a JSON artifact. |
| `panel.show` | `none` | `data, image, text, all` | Show one cached character panel. |
| `panel.showcase` | `none` | `data, image, text, all` | Show the cached public showcase summary. |
| `player.calendar` | `cookie` | `data, image, text, all` | Show authenticated player activity calendar data. |
| `player.characters` | `cookie` | `data, image, text, all` | Show authenticated player character details. |
| `player.diary` | `cookie` | `data, image, text, all` | Show authenticated monthly traveler diary data. |
| `player.inventory` | `cookie` | `data, image, text, all` | Show owned-character and equipped-weapon material counts. Coverage: `owned_character_ascension_and_equipped_weapon_materials`. |
| `player.register-time` | `cookie` | `data, text, all` | Attempt to show Genshin account registration time. Availability: `upstream-limited`. Limitations: Uses the legacy MYS anniversary endpoint, which may return provider retcode -502. |
| `player.summary` | `cookie` | `data, image, text, all` | Show authenticated player profile summary data. |
| `profile.default` | `none` | `data, text, all` | Set the default local profile. |
| `profile.delete` | `none` | `data, text, all` | Delete a local profile. |
| `profile.init` | `none` | `data, text, all` | Create or update a local profile. |
| `profile.list` | `none` | `data, text, all` | List local profiles. |
| `profile.show` | `none` | `data, text, all` | Show one local profile. |
| `progress.achievement-guide` | `none` | `data, text, all` | Look up GenshinUID achievement guide data. |
| `progress.achievements` | `cookie` | `data, image, text, all` | Show authenticated achievement category data. |
| `progress.collection` | `cookie` | `data, image, text, all` | Show authenticated collection count data. |
| `progress.commission-guide` | `none` | `data, text, all` | Look up GenshinUID commission achievement guide data. |
| `progress.completion` | `cookie` | `data, image, text, all` | Show authenticated account completion summary data. |
| `progress.exploration` | `cookie` | `data, image, text, all` | Show authenticated world exploration data. |
| `progress.gcg` | `cookie` | `data, image, text, all` | Show authenticated Genius Invokation TCG data. |
| `progress.gcg-deck` | `cookie` | `data, image, text, all` | Show authenticated Genius Invokation TCG deck data. |
| `rank.artifact` | `none` | `data, image, text, all` | Show the Akasha global artifact leaderboard. |
| `rank.character` | `none` | `data, image, text, all` | Show a character Akasha leaderboard or nearby UID rank rows. |
| `rank.list` | `none` | `data, image, text, all` | Render a UID's Akasha rank list. |
| `recommend.build` | `none` | `data, image, text, all` | Show GenshinUID character build recommendations. |
| `recommend.holder` | `none` | `data, image, text, all` | Show GenshinUID holder recommendations for a weapon or artifact. |
| `rerun.list` | `none` | `data, image, text, all` | List rerun rows and render the GenshinUID return list. |
| `wiki.artifact` | `none` | `data, image, text, all` | Look up public artifact set data. |
| `wiki.character` | `none` | `data, text, all` | Look up public character data. |
| `wiki.character-materials` | `none` | `data, image, text, all` | Show public character material data. |
| `wiki.constellation` | `none` | `data, image, text, all` | Look up public character constellation data. |
| `wiki.enemy` | `none` | `data, text, all` | Look up public enemy data. |
| `wiki.food` | `none` | `data, image, text, all` | Look up public food data. |
| `wiki.talent` | `none` | `data, text, all` | Look up public character talent data. |
| `wiki.weapon` | `none` | `data, image, text, all` | Look up public weapon data. |
| `wiki.weapon-materials` | `none` | `data, image, text, all` | Show public weapon material data. |