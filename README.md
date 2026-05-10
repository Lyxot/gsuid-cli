# gsuid-cli

> 本项目深受 [GenshinUID](https://github.com/KimigaiiWuyi/GenshinUID) 的启发，并在图片渲染设计与资产上深度复用了前者的卓越工作。

`gsuid` 是一个专为原神账号、公共数据、面板、祈愿记录及活动工作流设计的纯命令行工具（CLI）。它专为 AI 代理和自动化工具使用而设计，当然人类用户也可以轻松使用。目前主要支持国服（CN）数据。

该工具的标准输出契约为标准输出（stdout）中的 JSON 数据。所有的警告、进度和人类可读提示都会输出到标准错误（stderr）中。渲染的图片、地图及导出的文件等会被保存到本地磁盘中，并在 JSON 中返回其绝对路径。你可以运行 `meta capabilities` 命令查看哪些命令目前支持返回图片产物。

默认的渲染模式为 `data`，因此 JSON 输出会包含结构化的 `data` 和 `sources`。如果你只想要紧凑的产物包（不包含大量 JSON 数据），你可以选择非数据渲染模式，比如 `--render image` 或 `--render text`。加上 `--debug` 选项将会在本地生成包含完整细节的 `debug-envelope.json` 文件用于诊断。
如果添加了 `--format plain` 选项，文本渲染模式将直接在终端打印人类可读的文本，而图片渲染模式会打印生成的图片路径。

## 安装指南 (Installation Guide)

`gsuid-cli` 是一个基于 Python 的命令行工具，专为自动化脚本和 Agent 提供原神数据而设计。

### 环境要求

- **Python**: 3.11 或更高版本
- **操作系统**: macOS、Linux 或 Windows
- **凭据管理器 (Keyring)**: 操作系统必须提供安全的凭据管理器服务。在 Linux 系统上，可能需要安装 `dbus-x11` 和相应的 `keyring` 后端，例如 `gnome-keyring` 或 `kwallet`。

### 从源码安装 (推荐)

当前工具尚未发布至 PyPI，建议从源码克隆并使用虚拟环境进行安装。

#### 1. 克隆代码仓库

```sh
git clone https://github.com/Lyxot/gsuid-cli.git
cd gsuid-cli
```

#### 2. 创建并激活虚拟环境

为了避免依赖冲突，请务必使用 Python 虚拟环境。

```sh
python3 -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (Command Prompt)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

#### 3. 安装依赖与工具

如果你打算只使用工具，可以执行标准安装：

```sh
python3 -m pip install -e .
```

如果你希望参与开发、运行测试或查看代码规范，请安装开发者依赖：

```sh
python3 -m pip install -e ".[dev]"
```

### 安装验证

安装完成后，你可以通过运行以下命令来验证是否安装成功：

```sh
gsuid meta version
```

或者使用 Python 模块方式调用（在使用自动化 Agent 时更为推荐，因为它确保了使用的是当前环境的 Python）：

```sh
gsuid meta version
```

如果成功输出包含版本号和当前环境状态的 JSON 数据包，说明安装完成！

## 快速上手 (Quickstart)

本指南将带你从零开始配置 `gsuid-cli` 并执行第一次查询。

### 步骤一：初始化配置文件

`gsuid-cli` 通过“配置文件”(profile) 和“账号”(account) 的概念来管理多用户的状态。
首先，我们需要初始化默认配置文件，并绑定你的原神 UID：

```sh
# 1. 初始化一个默认配置，默认区服设定为国服 cn
gsuid profile init --name default --region cn

# 2. 将你的 UID 添加到账号列表
gsuid account add --uid 100000000 --region cn

# 3. 将这个 UID 设为默认账号
gsuid account default --uid 100000000
```

> **注意：** 请将上面的 `100000000` 替换为你真实的原神 UID。

### 步骤二：登录获取凭据

为了查询私人数据（例如树脂、背包、深渊等），你需要登录并获取米游社凭据。最安全便捷的方式是使用二维码登录。

```sh
gsuid auth qrcode login --uid 100000000
```

运行后，控制台会给出扫码提示，请使用米游社 APP 扫描屏幕上生成的二维码。扫码确认后，CLI 会自动获取 Cookie 和 Stoken，并安全存储在你的操作系统的凭据管理器中。

> 关于凭据存储的安全说明，请参考 [凭据安全指南](docs/credential-safety.md)。

### 步骤三：绑定设备（可选）

为了应对部分情况下可能出现的 `1034`、`5003`、`-999` 等风控错误码，你可以选择绑定常用的米游社设备信息，以尽可能减少验证码风控的出现。

你可以通过网络抓包获取带有 `fp` 和 `device_id` 等字段的设备信息（可能还会包含 `device_info` 或 `oaid`），然后将其构造为 JSON 字符串或文件，绑定到对应的 UID：

> **💡 提示：** 安卓用户可以直接使用第三方工具 [get_device_info](https://github.com/forchannot/get_device_info) 来获取自己的设备数据。

```sh
# 通过 JSON 字符串直接绑定
gsuid auth device set --uid 100000000 --device-json '{"fp":"38fff985f","device_id":"1234-5678-9999999-wcdd"}'

# 或者将 JSON 写入文件后，通过文件进行绑定
gsuid auth device set --uid 100000000 --device-file device.json
```

> **⚠️ 风险提示：** 绑定设备指纹可能存在一定未知风险，请谨慎使用，并确保使用的是你本人的常用设备信息。

### 步骤四：查询私人数据与生成图片

登录完成后，你可以尝试查询你的私人账号数据（如原粹树脂状态、深渊战绩等）。默认情况下，命令只会返回纯数据（JSON）：

```sh
# 查询实时便笺（树脂、洞天财瓮、每日委托等）
gsuid daily note

# 查询玩家账号基础信息汇总
gsuid player summary

# 查询当前赛季深境螺旋战绩
gsuid challenge abyss --season current

# 查询世界探索进度汇总
gsuid progress exploration
```

如果你希望生成 GenshinUID 风格的图片，只需增加 `--render image` 选项：

```sh
gsuid --render image daily note
gsuid --render image player summary
```

如果图片生成成功，JSON 返回结果的 `artifacts` 数组中将会包含一条记录，告诉你生成图片在本地的绝对路径。

如果你希望直接在终端中查看人类可读的文本结果（而不是 JSON 数据），请使用 `--render text --format plain` 选项：

```sh
gsuid --render text --format plain daily note
```

如果你想一次性获取全部渲染结果（包括文本产物和精美的图片），可以使用 `--render all`：

```sh
gsuid --render all daily note
```

### 步骤五：查询公开数据

你也可以查询不依赖个人账号的公开数据，例如角色攻略、每日副本材料分布或活动日历等：

```sh
# 查询安柏的攻略建议和突破材料
gsuid wiki character --name 安柏
gsuid guide character --name 安柏

# 查询当前正在进行和即将开始的活动
gsuid events list

# 查看近期祈愿池复刻信息
gsuid rerun list

# 生成今日材料副本列表的图片
gsuid --render image daily materials

# 查询当前可用的前瞻直播或常规兑换码
gsuid codes list
```

## 自动化批处理

对于自动化工具，CLI 提供了直接通过 JSONL 文件进行批量执行的功能：

```sh
printf '%s\n' \
  '{"id":"version","argv":["meta","version"]}' \
  '{"id":"paths","command":"meta paths"}' \
  | gsuid --request-id batch-1 batch run --file -
```

## 数据输出格式

所有成功的命令都会返回标准的 JSON 结构包：

```json
{
  "ok": true,
  "schema": "gsuid.cli/v1",
  "command": "meta.version",
  "request_id": "req",
  "generated_at": "2026-04-29T10:30:00Z",
  "duration_ms": 5,
  "warnings": [],
  "data": {},
  "artifacts": [],
  "sources": [
    {
      "provider": "local",
      "region": "cn",
      "cached": false,
      "fetched_at": "2026-04-29T10:30:00Z"
    }
  ],
  "pagination": null
}
```

即使执行失败，工具也会在 stdout 中输出对应的 JSON 错误包，并以非 0 状态码退出。可以使用以下命令查看元信息：

```sh
gsuid meta capabilities
gsuid meta schema --command daily.note
gsuid meta errors
```

## 进阶文档

更多深入信息，请查阅文档：

- [命令参考 (Command Reference)](docs/commands.md)
- [凭据安全指南 (Credential Safety)](docs/credential-safety.md)
- [HTTP 缓存策略 (Cache Policy)](docs/http-cache-policy.md)
- [架构设计 (Architecture)](docs/architecture.md)

## 代码检查和测试

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python scripts/generate_command_reference.py --check
```
