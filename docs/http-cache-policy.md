# HTTP 缓存策略 (HTTP Cache Policy)

本文档是数据源 HTTP 响应缓存的核心策略文件。如果策略需要调整，请首先修改本文档，然后同步更新 `src/gsuid_cli/core/cache_policy.py` 中的代码。如果涉及到 GenshinUID 镜像源选择的逻辑变动，还需要更新 `src/gsuid_cli/providers/resource_mirror.py`。

## 运行时缓存语义

- `--cache use`（默认）: 当存在未过期的缓存时直接使用缓存响应；否则向数据源发起请求，并在符合缓存规则的前提下将结果写入缓存。
- `--cache refresh`: 强制向数据源发起请求并覆盖现有缓存（前提是符合缓存规则）。对于依赖版本号的响应，仅当能够成功查询到 Sophon 构建标签（build tag）时才允许被持久化。
- `--cache only`: 仅返回现有的缓存响应。如果缓存已过期或不存在，命令将抛出 `CACHE_MISS` 错误。
- `--cache off`: 彻底跳过缓存读取与写入。
- **所有非 GET 请求都绝对不会被缓存。**
- 持久化的 JSON 响应会缓存在 `$GSUID_HOME/cache/http` 目录下。
- 二进制文件/静态资源会缓存在 `$GSUID_HOME/cache/<usage>` 目录下。资源的作用域 (usage) 包括 `assets`、`icons`、`maps` 以及 `wiki`。
- `game-version` 规则的缓存条目会记录当前的 `cache_version`。当通过检测发现最新的 Sophon 构建标签发生变化时，这些条目就会被视为过期。
- 当系统在运行中遇到已过期或版本陈旧的持久化缓存时，会自动将其删除。
- 缓存键 (Cache Key) 基于脱敏后的 URL 生成，且**绝对不能包含任何密钥或敏感参数**。
- 当前的 Sophon 构建标签通过请求 `https://api-takumi.mihoyo.com/downloader/sophon_chunk/api/getBuild?branch=main&package_id=8xfMve0uwQ&password=CW8GbLNU8f&plat_app=ddxf5qt290cg` 获取，取其 JSON 结果中的 `["data"]["tag"]` 字段。
- 形如 `genshinuid://` 开头的 GenshinUID 资源 URL 是逻辑地址。它们会采取延迟解析的方式寻找当前最快的镜像源进行下载；但是，缓存文件本身依旧采用逻辑 URL 进行索引，这确保了即便镜像源发生切换，本地缓存依然能够被复用。
- GenshinUID 的最优镜像测速缓存保存在 `$GSUID_HOME/cache/http/resource-mirror.genshinuid.json`。使用 `--cache refresh` 会重新测速并覆盖；`--cache off` 会测速但不会保存结果；`--cache only` 不会触发测速。

## 缓存过期规则

| 规则名称 | 过期策略 | 适用数据类型 |
| --- | --- | --- |
| `no-store` | 永不缓存。 | 登录、Token操作、设备验证等具有副作用的操作请求。 |
| `private-short` | 获取后 60 秒内有效，且仅驻留在进程内存中，不写入磁盘。 | 需要身份验证的玩家状态、深渊挑战、探索进度以及刷新抽卡记录时的分页请求。 |
| `public-short` | 获取后 5 分钟内有效。 | 变化较快的公开数据（如排行榜、面板查询）及轻量级健康检查。 |
| `public-dynamic` | 获取后 6 小时内有效。 | 公开的游戏活动、游戏公告、复刻记录以及兑换码。 |
| `daily-reset` | 到达次日国服日常刷新时间 (UTC+8 凌晨 04:00) 后过期。 | 每日天赋/武器突破材料排期。 |
| `game-version-tag` | 到达次日国服刷新时间 (UTC+8 凌晨 06:00) 后过期。 | Sophon 的游戏构建标签，用作 `game-version` 规则的校验标准。 |
| `game-version` | 当本地存储的 `cache_version` 与 `game-version-tag` 取回的最新构建标签不一致时过期。 | 公开的 Wiki、攻略、推荐搭配数据，以及通常只随游戏版本大更新才会发生变动的渲染用静态资源。 |
| `resource-mirror` | 测速后 6 小时内有效。 | 专门用于 GenshinUID 镜像源测速结果的缓存（实际下载的资源负载依然遵循 `game-version` 等其他规则）。 |

## 接口地址 (URL Family) 映射

| 接口家族 | 适用规则 | 备注说明 |
| --- | --- | --- |
| `auth.*`, `device.*`, `daily.signin*`, `daily.bbs-coin*`, `gacha.authkey.refresh` | `no-store` | 登录、签到、米游币任务和设备绑定状态相关的数据必须保证绝对实时。 |
| `daily.note*` | `private-short` | 树脂、探索派遣、委托等玩家状态不应当长期保留或落盘。 |
| `player.*`, `challenge.*`, `progress.*`, `gacha.refresh` | `private-short` | 拦截短时间内的重复并发请求，同时又不影响正常账号状态的变更获取，保护私有数据不落盘。 |
| `rank.*`, Akasha 提供商的 JSON | `public-short` | 玩家排行榜的变动非常频繁。 |
| `panel.refresh`, Enka 提供商的 JSON | `public-short` | 展柜面板在玩家调整角色展示后随时可能改变。 |
| `daily.materials`, `daily.materials.upgrade` | `daily-reset` | 日常副本的排期在凌晨 04:00(UTC+8) 会发生轮换。 |
| `codes.*`, `events.*`, `announcements.*`, `rerun.*` | `public-dynamic` | 属于公开数据，但在同一版本期间内也可能会发生变动。 |
| Sophon `getBuild` 接口 | `game-version-tag` | 读取 `data.tag` 并每天早上 06:00(UTC+8) 更新。 |
| `genshinuid://*` 逻辑资源 URL | 测速时采用 `resource-mirror` 规则；实际拉取资源时继承该资源业务场景原本的规则。 | 在需要下载文件时才会动态解析并绑定到当前最快镜像。通常公共资源走 `game-version` 规则，玩家私有类别下的可能采用更短的规则。 |
| `wiki.*`, `guide.*`, `recommend.*` | `game-version` | 静态攻略和百科数据通常在游戏大版本更新时才会发生变化。 |
| 基于 Github/jsDelivr 裸请求的 `guide.*` 资源 | `game-version` | 例如请求 `GenshinUID/genshinuid_guide/abyss.js` 时，会先通过 API 获取默认分支下该路径的最新 Commit Hash，随后通过 jsDelivr 获取文件内容。 |
| 通过 `request_bytes` 下载的二进制静态资源 | `game-version` | 包含了 GenshinUID、AMBR、Hakush、MiniGG、米游社图标等各类渲染所需的图片资源（除非另行指定了更严格的规则）。 |
| `meta.doctor.network` | `public-short` | 仅用于验证数据源的连通性健康检查。 |

## 资源缓存作用域 (Usage Bucket) 映射

| 作用域 (Usage) | 适用的接口或业务场景 |
| --- | --- |
| `icons` | URL 中包含 `icon`、以 `.avatar` 结尾、包含 `profile_picture` 的请求，AMBR/Hakush/米游社的 UI 图标资源，以及 `genshinuid://resource/icon*` 目录下的资源。 |
| `maps` | MiniGG 提供的地图资源以及 `map.*` 系列接口请求。 |
| `wiki` | `genshinuid://wiki/*` 目录资源，以及所有非图标 (non-icon-like) 的百科、攻略、活动、公告、配队推荐、复刻记录和每日材料资源。 |
| `assets` | 默认的通用资源存放桶，包括 `genshinuid://resource/*` 目录下共用的角色、武器、卡牌等渲染所需杂项资源。 |

## 缓存策略修改流程

1. **首先编辑此 Markdown 策略文档。**
2. 同步更新 `src/gsuid_cli/core/cache_policy.py` 中的代码实现。
3. 增加或修改对应的缓存行为单元测试。
4. 运行相关的单元测试以验证修改是否生效；如果修改了命令接口，记得运行 `scripts/generate_command_reference.py --check` 命令校验文档一致性。
