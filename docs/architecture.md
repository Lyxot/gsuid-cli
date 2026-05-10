# 架构与开发规范 (Architecture & Development)

`gsuid-cli` 是一个采用模块化设计的命令行工具，主要分为命令层 (Commands)、服务层 (Services)、数据源 (Providers) 以及渲染器 (Renderers)。
本文件详细记录了核心的架构原则、实施规则以及为将来的 AI 代理和开发者指定的开发准则。

## 1. 系统架构与包结构

```text
src/gsuid_cli/
  __init__.py
  __main__.py
  cli.py                # 命令行入口与全局参数解析
  commands/             # 命令层：解析参数、调用提供商并整合渲染
    account.py          # 本地账号管理
    auth.py             # 凭据(登录/验证)管理
    batch.py            # 自动化批量执行 JSONL
    cache.py            # 缓存诊断与清理
    challenge.py        # 挑战玩法 (深渊、剧诗、深罪旋曜)
    gacha.py            # 祈愿记录管理
    meta.py             # 元信息和诊断命令
    monitor.py          # 自动化监控与轮询
    player/             # 玩家核心数据命令 (汇总、背包、角色)
      __init__.py       # 命令组门面：导出 CAPABILITIES/register
      impl.py           # player 命令实现
      assets.py         # 玩家渲染资源收集与 Enka/MYS 辅助
    panel/              # 角色展柜与面板管理
      __init__.py       # 命令组门面：导出 CAPABILITIES/register
      capabilities.py   # panel 子命令能力声明
      register.py       # argparse 子命令注册
      impl.py           # panel 命令实现
      cache.py          # 本地 panel_cache 读写与标准化
      common.py         # panel 子模块共享的小工具
      enrichment.py     # 公共数据补全 (如武器效果/角色名)
      mys.py            # 米游社面板数据适配
    profile.py          # 配置档案管理
    progress.py         # 进度玩法 (探索、成就、七圣)
    public_data/        # 公共数据命令组
      daily.py          # 日常状态 (便笺、签到、材料)
      events.py         # 活动、公告与兑换码
      guide.py          # 攻略建议与路线
      wiki.py           # 百科数据
    rank.py             # Akasha 排名
  core/                 # 核心模块：通用系统与基础设施
    artifacts.py        # 本地文件与产物管理
    cache.py            # HTTP 和文件缓存
    cache_policy.py     # HTTP 缓存 TTL/日重置/版本化策略
    config.py           # 本地环境配置路径
    envelope.py         # JSON 契约包装
    errors.py           # 标准错误定义
    http.py             # HTTP 客户端封装与来源捕获
    models.py           # 核心数据模型 (CommandResult等)
    region.py           # UID/地区解析
    render.py           # render 模式判定与数据合并
    schemas.py          # JSON schema 辅助
    secrets.py          # 凭据存储 (Keyring)
    state.py            # SQLite 本地状态管理
    time.py             # 时间处理
  providers/            # 数据提供商：处理 HTTP 和第三方 API 逻辑
    akasha.py           # Akasha 排行
    assets.py           # 渲染资源下载
    enka.py             # Enka 面板
    resource_mirror.py  # GenshinUID/资源镜像解析
    mys/                # 官方米游社 API 子模块
    public/             # 公共数据提供商与各数据域解析
  renderers/            # 渲染层：将数据转化为图片或直观文本
    common.py           # 图像/文本渲染通用工具
    _text_helpers.py    # 文本渲染基础格式化函数
    challenge/          # 深渊、剧诗、深罪旋曜图片/文本渲染
    daily/              # 便笺、材料、签到渲染
    events/             # 活动/公告渲染 (image.py + text.py)
    guide/              # 攻略卡片/文本渲染 (image.py + text.py)
    panel/              # 角色面板图片、文本、指标
    player/             # 玩家汇总、背包、日历、角色等渲染
    progress/           # 探索、成就、七圣渲染
    rank/               # Akasha 排名渲染 (image.py + text.py)
    wiki/               # 百科图文渲染
```

## 2. 依赖决策

- **CLI 解析**: 首选标准库 `argparse`，以防止外部框架的行为污染 stdout 导致自动化解析失败。
- **HTTP**: 使用 `httpx` 处理所有网络请求。
- **凭据存储**: 强制使用 `keyring`；不实现任何本地明文密钥的后备方案。
- **数据验证**: 优先使用原生的 `dataclasses` 和明确的序列化函数。仅当第三方提供的数据模型难以维护时，才考虑引入 `Pydantic`。
- **本地存储**: 对于状态和缓存元数据，使用标准库的 `sqlite3`。
- **TOML**: 使用 `tomllib` 读取配置。若需要写入操作则使用 `tomli-w`。
- **代码规范**: 使用 `ruff` 检查和格式化。
- **测试**: 使用 `pytest`，并借助 `respx` 或 `pytest-httpx` 拦截 HTTP 请求。
- **图像渲染**: 使用 `Pillow` 进行图像组合与绘制。

## 3. 开发准则与服务层规范

### 服务层/命令层
- 命令模块 (`commands/*.py`) 负责解析输入参数并调用提供商 (Providers)。
- 所有调用必须返回普通的 Python 模型对象（如 `CommandResult`），不能直接返回 JSON 字符串。
- 渲染器 (`renderers/`) 接收这些 Python 模型并生成最终的产物（图像/文本文件）。
- 输出包装 (JSON Envelope) 在命令层的最终边界统一执行。
- 每项命令默认必须支持非交互式调用，完全适配自动化机器人和 Agent。

### 数据源规则 (Providers)
- Provider 专门处理 HTTP 请求、构建验证头 (Headers)、执行重试和处理上游特殊逻辑。
- Provider **绝对禁止**直接将产物文件写入磁盘。
- 所有的 Provider 网络请求必须明确设定超时时间 (Timeout)。
- Provider 在返回的 `source` 对象中必须包含提供商来源、URL 类别、状态码 (Status code)、是否命中缓存 (`cached`) 以及拉取时间 (`fetched_at`)。
- 缓存键 (Cache Keys) 的构建必须剥离所有的身份密钥和敏感参数。
- 默认情况下仅对安全且具备幂等性 (Idempotent) 的 GET 请求执行重试。
- 诸如签到等带有副作用的 POST 动作禁止自动重试，除非返回结果能明确证实操作已被安全忽略。

### 数据范式
- 为了避免部分语言和终端进行错误的数字转换，所有的 UID 在 JSON 中必须作为 **字符串** (`String`) 处理。
- 时间戳统一采用带有 `Z` 后缀的 UTC ISO 8601 格式。
- 持续时间单位统一采用**秒** (Seconds)，除非字段名称中明确标注了其他单位（如 `duration_ms`）。
- 货币、积分或代币相关的数量强制使用整数 (Integers)。
- 百分比数值采用从 `0` 到 `100` 之间的实数表示。
- 如果上游缺失某些字段，但该字段属于预期的 schema 契约内，必须显式返回 `null` 而不是直接删除该键。

## 4. 产品与设计决策

### 核心定位
构建一个 Python 编写的 CLI 工具 `gsuid`，功能覆盖原神账号管理、百科、面板、抽卡记录以及活动数据等。其设计灵感来自于 GenshinUID 插件，但 `gsuid` **专为了满足 Agent、工具链或自动化流水线的使用而设计，而不是做一个交互式的聊天机器人**。

### 非目标 (Non-Goals)
- 不实现 QQ/OneBot/Telegram/WeChat 等任何聊天机器人的适配层。
- 不强制要求以交互式提示作为必要的工作流。
- 不以聊天风格的指令别名作为稳定的命令契约。
- 不在当前 MVP 版本中实现充值或支付等敏感流程。
- 不在当前 MVP 版本中增加插件自我更新的功能。
- 在单次执行和批处理模式稳定之前，不添加任何常驻进程守护 (Daemon)。

### 假设与约束
- 当前版本目标仅为《原神》 (Genshin Impact)。
- 首发 MVP 版本仅支持国服 (CN)，海外 HoYoLAB 的支持会在未来添加。
- 本地配置和自动绑定账号只是为了便于人类使用，大多数命令都可以且应当通过显式传递 `--uid` 参数运行。
- 对于渲染生成的图像，尽可能争取在视觉表现上与 GenshinUID 原始功能看齐。
- 在满足开源协议兼顾署名的情况下，允许参考甚至复用 GenshinUID 的部分静态资源或处理逻辑。

## 5. 自动化开发代理操作指南 (Rules For Future Agents)

如果在后续的开发任务中启用了新的 AI Agent：
- **执行原则**：优先遵循既有实现模式；除非代码缺乏测试覆盖，否则请先保障旧有逻辑不被破坏再考虑重构。
- **提交规范**：严格使用 [Conventional Commits](https://www.conventionalcommits.org/)，每次完成一个实质性阶段请单独进行一次原子提交 (Commit)。
- **隔离环境**：执行 Python 命令时强制使用仓库本地目录的虚拟环境 `.venv/bin/python`。不得将虚拟环境产生的文件包含进 `git` 提交中。
- **授权协议**：若全盘复制 GenshinUID 的代码或资源，必须首先评估并明确解决版权许可兼容及引用署名问题。
