# 安装指南 (Installation Guide)

本文档记录 `gsuid-cli` 的安装方式。推荐使用 `uv`，传统 `venv + pip` 和 requirements 风格安装仍可用于旧环境或特殊部署系统。

## 环境要求

- Python 3.11 或更高版本。
- macOS、Linux 或 Windows。
- 凭据管理器 (Keyring)：用于安全保存 Cookie、Stoken、祈愿 URL 等敏感数据。
- Linux 桌面/服务器可能需要安装 `dbus-x11` 以及 `gnome-keyring`、`kwallet` 等 keyring 后端。

## 推荐方式: uv

### 安装 uv

macOS:

```sh
brew install uv
```

Linux/macOS 通用脚本:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 克隆仓库

```sh
git clone https://github.com/Lyxot/gsuid-cli.git
cd gsuid-cli
```

### 同步运行环境

普通使用:

```sh
uv sync --python 3.11
```

开发、测试、格式检查:

```sh
uv sync --python 3.11 --extra dev
```

### 验证安装

```sh
uv run gsuid meta version
uv run python -m gsuid_cli meta version
```

如果命令输出 JSON 包并包含版本信息，说明安装成功。

### 常用开发命令

```sh
uv run --python 3.11 --extra dev python -m pytest
uv run --python 3.11 --extra dev ruff check .
uv run --python 3.11 --extra dev ruff format --check .
uv run --python 3.11 --extra dev python scripts/generate_command_reference.py --check
uv build --python 3.11
```

## 传统方式: venv + pip

此方式不使用 `uv.lock`，依赖会由 pip 按 `pyproject.toml` 重新解析。只在无法使用 `uv` 的环境中使用。

macOS/Linux:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
gsuid meta version
```

Windows Command Prompt:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .
gsuid meta version
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
gsuid meta version
```

开发依赖:

```sh
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
ruff format --check .
```

## Requirements 风格安装

仓库不包含 `requirements.txt`，避免它和 `pyproject.toml` / `uv.lock` 同时成为依赖来源。若部署平台只能读取 requirements 文件，可以从锁文件导出临时文件。

运行时依赖:

```sh
uv export --locked --format requirements.txt --no-dev --no-emit-project --output-file /tmp/gsuid-cli-requirements.txt
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r /tmp/gsuid-cli-requirements.txt
python -m pip install --no-deps -e .
gsuid meta version
```

开发依赖:

```sh
uv export --locked --format requirements.txt --extra dev --no-emit-project --output-file /tmp/gsuid-cli-requirements-dev.txt
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r /tmp/gsuid-cli-requirements-dev.txt
python -m pip install --no-deps -e .
python -m pytest
```

Windows 用户可将 `/tmp/...` 换成 `%TEMP%\...` 或项目外的任意临时路径。

## 本地数据目录

默认本地目录为 `~/.gsuid-cli`，可通过 `GSUID_HOME` 改写：

```sh
export GSUID_HOME="$HOME/.gsuid-cli"
```

常见文件:

```text
config.toml
state.sqlite
cache/
artifacts/
logs/
```

`config.toml` 只保存非敏感默认值。Cookie、Stoken、祈愿 URL 等敏感数据通过 keyring 保存。

## 故障排查

- `ModuleNotFoundError`: 确认命令是在 `uv run ...` 或已激活的 `.venv` 中执行。
- `No recommended backend was available` / keyring 错误: 安装或启用系统凭据管理器后重试。
- Linux 无桌面环境: 可能需要配置 Secret Service、KWallet 或使用系统支持的 keyring 后端。
- `docs/commands.md is out of date`: 执行 `uv run --python 3.11 --extra dev python scripts/generate_command_reference.py` 后再检查。

