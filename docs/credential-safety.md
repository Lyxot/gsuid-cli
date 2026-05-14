# 凭据安全指南 (Credential Safety)

`gsuid` 在运行过程中会处理诸如 Cookie、Stoken、祈愿认证 URL (authkey)、二维码登录票据 (ticket)、设备指纹 (device fingerprints) 以及其他派生的令牌数据。**请将这些数据均视为绝密或私人账号数据进行保护。**

## 存储规则

- 所有存储的凭据**必须**使用操作系统的安全凭据管理器 (Keyring) 进行保存。
- 本 CLI **不会**提供任何形式的明文凭据降级存储方案。
- 如果无法访问操作系统的凭据管理器，执行读取或写入凭据的命令时会直接抛出 `KEYRING_UNAVAILABLE` 错误并失败。
- 支持使用一次性的环境变量为单条命令提供凭据（环境变量中的凭据优先级最高且不会被存储）。

支持的一次性环境变量如下：

```text
GSUID_COOKIE
GSUID_STOKEN
GSUID_GACHA_URL
```

## 隐私脱敏规则

CLI 在任何时候都**禁止**在输出中打印完整的 Cookie、Stoken、祈愿 URL、游戏令牌、二维码票据、设备指纹或包含 `authkey` 查询参数的 URL。执行成功的命令输出中只会包含部分脱敏的预览信息以及凭据的存储状态。

**强烈建议：** 永远不要把完整的敏感凭据粘贴到 GitHub Issue、日志、Git 提交记录、屏幕截图或批处理文件中。如果需要在本地测试，建议优先使用二维码扫码登录或通过环境变量临时传递。

## 推荐的登录流程

在条件允许的情况下，请始终使用交互式的二维码登录：

```sh
gsuid auth qrcode login --uid <你的UID>
```

该命令会在标准错误流 (stderr) 中打印二维码的扫码说明，并在扫码成功后，自动在标准输出 (stdout) 返回 JSON 结果，同时自动将获取到的 Cookie 和 Stoken 安全存储至操作系统的凭据管理器中。

对于非交互式的自动化编排，也可以拆分执行手动扫码流程：

```sh
gsuid auth qrcode start
gsuid auth qrcode poll --app-id APP --ticket TICKET --device DEVICE
gsuid auth qrcode complete --uid <UID> --app-id APP --ticket TICKET --device DEVICE
```

由于二维码登录票据有效期很短，人工操作时建议直接使用 `auth qrcode login`，它会在展示二维码后立即自动开始轮询。

## 自动化脚本与批处理文件 (Batch Files)

你可以通过批处理文件来批量执行需要认证的命令。但请注意：**绝对不要在批处理输入的 JSONL 文件中直接硬编码包含凭据内容。**
正确的方法是让 CLI 从本地凭据管理器自动读取凭据，或者在执行批处理命令的外部环境通过环境变量短时间注入凭据。

**错误示例 (绝对不要这样做)：**

```json
{"argv":["auth","cookie","set","--uid","<UID>","--cookie","真实的secret_cookie"]}
```

**正确示例：**

```json
{"argv":["daily","note","--uid","<UID>"],"request_id":"daily-1"}
```

## 本地文件结构

CLI 默认的本地状态和数据存放在 `$GSUID_HOME` 目录下（如果未设置环境变量，默认为 `~/.gsuid-cli`）：

```text
config.toml          # 存放非敏感的配置参数
state.sqlite         # 存放账号、配置档案、缓存元数据和祈愿记录摘要
cache/               
  assets/            # 存放通用的静态资源缓存
  icons/             # 存放图标资源缓存
  maps/              # 存放地图资源缓存
  wiki/              # 存放 wiki 资源缓存
artifacts/           # 存放生成的渲染图片、导出的日志等产物
logs/                # 存放日志文件
```

SQLite 状态文件 (`state.sqlite`) 仅用于存储非敏感的账号和配置文件元数据。
配置文件 (`config.toml`) 仅用于存储 CLI 全局默认值，例如输出格式、渲染模式、缓存策略、超时时间和文本语言；不要在其中保存 Cookie、Stoken 或抓包 URL。
静态资产缓存 (`cache/`) 会存储可复用的公共静态文件以及下载重试元数据。
产物目录 (`artifacts/`) 会包含渲染的账号详情图片、导出的抽卡记录和地图等，**请将产物目录视为私人的本地数据妥善保管**。你可以运行 `meta capabilities` 命令来查看哪些命令会生成图片等产物文件。
