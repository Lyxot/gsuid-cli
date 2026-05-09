# Command Reference

Generated from `gsuid meta capabilities`.

| Command | Auth | Render | Description |
| --- | --- | --- | --- |
| `account.add` | `none` | `data, text, all` | 添加或更新账号。 |
| `account.default` | `none` | `data, text, all` | 设置默认账号。 |
| `account.list` | `none` | `data, text, all` | 列出账号。 |
| `account.remove` | `none` | `data, text, all` | 移除账号。 |
| `account.show` | `none` | `data, text, all` | 显示账号。 |
| `announcements.list` | `none` | `data, image, text, all` | 列出公开的游戏公告。 |
| `announcements.show` | `none` | `data, image, text, all` | 显示单条公开的公告。 |
| `auth.cookie.delete` | `keyring` | `data, text, all` | 从操作系统凭据管理器中删除已存储的 Cookie。 |
| `auth.cookie.set` | `keyring` | `data, text, all` | 将 Cookie 存储在操作系统凭据管理器中。 |
| `auth.cookie.test` | `cookie` | `data, text, all` | 在国服数据源处验证 Cookie 是否可用。 |
| `auth.device.delete` | `none` | `data, text, all` | 删除本地米游社设备元数据。 |
| `auth.device.set` | `cookie` | `data, text, all` | 绑定并存储米游社设备元数据。 |
| `auth.device.test` | `device` | `data, text, all` | 检查本地米游社设备元数据可用性。 |
| `auth.gacha-url.delete` | `keyring` | `data, text, all` | 从操作系统凭据管理器中删除已存储的祈愿 URL。 |
| `auth.gacha-url.set` | `keyring` | `data, text, all` | 将祈愿 URL 存储在操作系统凭据管理器中。 |
| `auth.gacha-url.test` | `gacha_url` | `data, text, all` | 检查本地祈愿 URL 的可用性，不进行数据源验证。 |
| `auth.qrcode.complete` | `keyring` | `data, text, all` | 完成已确认的二维码登录。 |
| `auth.qrcode.login` | `keyring` | `data, image, text, all` | 运行交互式二维码登录。 |
| `auth.qrcode.poll` | `none` | `data, text, all` | 轮询一次二维码登录会话。 |
| `auth.qrcode.start` | `none` | `data, image, text, all` | 创建二维码登录会话。 |
| `auth.stoken.delete` | `keyring` | `data, text, all` | 从操作系统凭据管理器中删除已存储的 Stoken。 |
| `auth.stoken.set` | `keyring` | `data, text, all` | 将 Stoken 存储在操作系统凭据管理器中。 |
| `auth.stoken.test` | `stoken` | `data, text, all` | 检查本地 Stoken 的可用性，不进行数据源验证。 |
| `batch.plan` | `none` | `data, text, all` | 验证 JSONL 批处理命令。 |
| `batch.run` | `mixed` | `data, text, all` | 执行 JSONL 批处理命令。 |
| `cache.clear` | `none` | `data, text, all` | 清理本地缓存文件。 |
| `cache.size` | `none` | `data, text, all` | 显示本地缓存和产物的磁盘使用情况。 |
| `challenge.abyss` | `cookie` | `data, image, text, all` | 显示深境螺旋数据。 |
| `challenge.hard` | `cookie` | `data, image, text, all` | 显示深罪旋曜挑战数据。 |
| `challenge.hard-rank` | `none` | `data, text, all` | 显示 Akasha 深罪旋曜排名。 |
| `challenge.theater` | `cookie` | `data, image, text, all` | 显示幻想真境剧诗数据。 |
| `codes.list` | `none` | `data, text, all` | 列出当前可用的兑换码。 |
| `daily.bbs-coin` | `stoken` | `data, text, all` | 运行并报告米游社通行币任务状态。 |
| `daily.materials` | `none` | `data, image, text, all` | 列出今日天赋和武器突破材料秘境。 |
| `daily.note` | `cookie` | `data, image, text, all` | 显示当前账号日常状态。 |
| `daily.signin` | `cookie` | `data, text, all` | 领取或报告米游社每日签到状态。 |
| `events.banners` | `none` | `data, image, text, all` | 列出活动横幅图片 URL。 |
| `events.list` | `none` | `data, image, text, all` | 列出正在进行和即将开始的活动。 |
| `gacha.authkey` | `gacha_url` | `data, text, all` | 显示已存储的祈愿 URL 状态。 |
| `gacha.authkey.refresh` | `cookie+stoken` | `data, text, all` | 使用 Cookie 和 Stoken 生成并存储祈愿 URL。 |
| `gacha.export` | `none` | `data, text, all` | 导出本地祈愿记录。 |
| `gacha.import` | `none` | `data, text, all` | 导入 UIGF 祈愿记录。 |
| `gacha.refresh` | `gacha_url` | `data, text, all` | 刷新本地祈愿记录。 |
| `gacha.summary` | `none` | `data, image, text, all` | 显示本地祈愿记录。 |
| `guide.abyss` | `none` | `data, image, text, all` | 显示深境螺旋攻略数据。 |
| `guide.character` | `none` | `data, image, all` | 显示角色攻略内容。 |
| `guide.reference-panel` | `none` | `data, image, all` | 显示角色的参考面板。 |
| `guide.route` | `none` | `data, image, all` | 获取材料讨伐路线图。 |
| `guide.theater` | `none` | `data, image, text, all` | 显示幻想真境剧诗攻略数据。 |
| `map.find` | `none` | `data, image, all` | 获取资源分布图。 |
| `meta.capabilities` | `none` | `data, text, all` | 显示已实现的功能信息。 |
| `meta.doctor` | `none` | `data, text, all` | 运行本地诊断。 |
| `meta.errors` | `none` | `data, text, all` | 显示稳定的错误元信息。 |
| `meta.paths` | `none` | `data, text, all` | 显示解析后的本地路径。 |
| `meta.schema` | `none` | `data, text, all` | 显示 JSON 数据包的 schema 元信息。 |
| `meta.version` | `none` | `data, text, all` | 显示版本元信息。 |
| `misc.primogems-plan` | `none` | `data, image, all` | 显示原石获取预估图。 |
| `monitor.once` | `none` | `data, text, all` | 运行一次本地健康检查。 |
| `panel.artifacts` | `none` | `data, image, text, all` | 列出已缓存的圣遗物。 |
| `panel.compare` | `none` | `data, image, text, all` | 对比已缓存的面板。 |
| `panel.graduation` | `none` | `data, image, text, all` | 汇总本地毕业度数据。 |
| `panel.list` | `none` | `data, text, all` | 列出已缓存的面板。 |
| `panel.refresh` | `none` | `data, text, all` | 刷新面板数据。 |
| `panel.save` | `none` | `data, text, all` | 保存已缓存面板的 JSON 产物。 |
| `panel.show` | `none` | `data, image, text, all` | 显示一个已缓存的面板。 |
| `panel.showcase` | `none` | `data, image, text, all` | 显示已缓存的展柜汇总。 |
| `player.calendar` | `cookie` | `data, image, text, all` | 显示玩家活动日历数据。 |
| `player.characters` | `cookie` | `data, image, text, all` | 显示玩家角色详情。 |
| `player.diary` | `cookie` | `data, image, text, all` | 显示旅行者札记数据。 |
| `player.inventory` | `cookie` | `data, image, text, all` | 显示已拥有角色和已装备武器的材料数量。 Coverage: `owned_character_ascension_and_equipped_weapon_materials`. |
| `player.register-time` | `cookie` | `data, text, all` | 尝试显示原神账号注册时间。 Availability: `upstream-limited`. Limitations: 使用旧版米游社周年庆接口，可能返回数据源错误码 -502。 |
| `player.summary` | `cookie` | `data, image, text, all` | 显示玩家资料汇总数据。 |
| `profile.default` | `none` | `data, text, all` | 设置默认配置文件。 |
| `profile.delete` | `none` | `data, text, all` | 删除配置文件。 |
| `profile.init` | `none` | `data, text, all` | 创建或更新配置文件。 |
| `profile.list` | `none` | `data, text, all` | 列出配置文件。 |
| `profile.show` | `none` | `data, text, all` | 显示一个配置文件。 |
| `progress.achievement-guide` | `none` | `data, text, all` | 查找成就攻略数据。 |
| `progress.achievements` | `cookie` | `data, image, text, all` | 显示成就分类数据。 |
| `progress.collection` | `cookie` | `data, image, text, all` | 显示收集进度数据。 |
| `progress.commission-guide` | `none` | `data, text, all` | 查找委托攻略数据。 |
| `progress.completion` | `cookie` | `data, image, text, all` | 显示账号完成度汇总。 |
| `progress.exploration` | `cookie` | `data, image, text, all` | 显示世界探索数据。 |
| `progress.gcg` | `cookie` | `data, image, text, all` | 显示七圣召唤数据。 |
| `progress.gcg-deck` | `cookie` | `data, image, text, all` | 显示七圣召唤卡组数据。 |
| `rank.artifact` | `none` | `data, image, text, all` | 显示圣遗物排行榜。 |
| `rank.character` | `none` | `data, image, text, all` | 显示角色排行榜。 |
| `rank.list` | `none` | `data, image, text, all` | 显示指定 UID 的排行列表。 |
| `recommend.build` | `none` | `data, image, text, all` | 显示角色养成建议。 |
| `recommend.holder` | `none` | `data, image, text, all` | 显示武器或圣遗物的建议使用者。 |
| `rerun.list` | `none` | `data, image, text, all` | 列出祈愿池复刻信息。 |
| `wiki.artifact` | `none` | `data, image, text, all` | 查询公开的圣遗物套装数据。 |
| `wiki.character` | `none` | `data, text, all` | 查询公开的角色数据。 |
| `wiki.character-materials` | `none` | `data, image, text, all` | 显示角色突破材料数据。 |
| `wiki.constellation` | `none` | `data, image, text, all` | 查询公开的角色命座数据。 |
| `wiki.enemy` | `none` | `data, text, all` | 查询公开的怪物数据。 |
| `wiki.food` | `none` | `data, image, text, all` | 查询公开的食物数据。 |
| `wiki.talent` | `none` | `data, text, all` | 查询公开的角色天赋数据。 |
| `wiki.weapon` | `none` | `data, image, text, all` | 查询公开的武器数据。 |
| `wiki.weapon-materials` | `none` | `data, image, text, all` | 显示武器突破材料数据。 |