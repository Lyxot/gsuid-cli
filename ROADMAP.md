# 开发路线图 (ROADMAP)

本项目采用阶段性推进方式，以下是已完成和待完成的开发阶段。

## 已完成的开发阶段

### Stage 0: Repository Bootstrap — completed.
### Stage 1: Specification Plan — completed.
### Stage 2: Project Skeleton — completed.
### Stage 3: State, Profiles, Accounts, And Secrets — completed.
### Stage 4: Provider Foundation — completed.
### Stage 4.5: QR Login — completed.
### Stage 4.6: Interactive QR Login — completed.
### Stage 4.7: Live Auth Validation Fixes — completed.
### Stage 4.8: MYS Device Login — completed.
### Stage 5: Public Data MVP — completed.
### Stage 6: Authenticated Daily And Player Data — completed.
### Stage 7: Progress And Challenge Data — completed.
### Stage 7.1: Challenge Abyss Image Renderer Fix — completed.
### Stage 8: Gacha Log — completed.
### Stage 8.1: Automatic Gacha Authkey URL — completed.
### Stage 8.1a: Refresh Expired Gacha Authkeys During Refresh — completed.
### Stage 8.2: Live Gacha Refresh Normalization — completed.
### Stage 8.3: Gacha Five-Star Intervals — completed.
### Stage 8.4: Gacha Refresh Gap Recovery — completed.
### Stage 9: Enka Panels And Ranking — completed.
### Stage 10: Rendering And Artifacts — completed.
### Stage 11: Guides, Maps, And Rich Public Data — completed.
### Stage 12: Batch And Agent Hardening — completed.
### Stage 13: Documentation, CI, And Release — completed.
### Stage 13.1: Chinese Localization Of User-Facing Strings — completed.
### Stage 14: Missing Command Contract Completion — completed.
### Stage 14.1: Source-Limited Player Data Ports — completed.
### Stage 14.2: Source-Limited Command Completion — completed.
### Stage 15: Full Global Options — completed.
### Stage 16: Help Information Coverage — completed.
### Stage 16.5: Cache System Redesign — completed.
### Stage 16.6: HTTP Cache Expiration Policy — completed.
### Stage 16.7: GenshinUID Resource Mirrors — completed.
### Stage 17: GenshinUID Image Parity — completed.
### Stage 18: Text Output And Result Surface Refactor — completed.
### Stage 18b: Text Render Artifacts — completed.
### Stage 18c: Public Data Text Render Artifacts — completed.
### Stage 18d: Wiki Text Render Artifacts — completed.
### Stage 18e: Guide, Recommendation, And Rerun Text Render Artifacts — completed.
### Stage 18f: Player Text Render Artifacts — completed.
### Stage 18g: Challenge Text Render Artifacts — completed.
### Stage 18h: Progress Text Render Artifacts — completed.
### Stage 18i: Gacha Text Render Artifacts — completed.
### Stage 18j: Local Profile, Account, And Auth Text Render Artifacts — completed.
### Stage 18k: Panel Text Render Artifacts — completed.
### Stage 18l: Rank Text Render Artifacts — completed.
### Stage 18m: Remaining Utility Text Render Artifacts — completed.
### Stage 19: HoYoLAB OS Region Support — completed.

## MVP 完成标准 (MVP Cut Line)

第一阶段可用的 MVP 标准在 Stage 6 之后已达成，以下命令均工作正常：

```text
gsuid meta version
gsuid meta capabilities
gsuid profile init
gsuid account add
gsuid auth cookie set
gsuid auth cookie test
gsuid wiki character
gsuid wiki weapon
gsuid events list
gsuid codes list
gsuid daily materials
gsuid daily note
gsuid player summary
gsuid player characters
```

**MVP 成功标准：**

- 所有实现的命令都能返回标准的 JSON envelope。
- 缺乏认证时必须返回退出码 `2` 和错误 `AUTH_REQUIRED`。
- 无效参数必须返回退出码 `1` 和错误 `INVALID_ARGUMENT`。
- 上游请求提供商发生错误时不会产生 Python 追踪堆栈信息 (除非开启了 `--debug` 模式)。
- 单元测试涵盖解析器、数据包层、错误类和提供商 Mocks。

## 待确定的后续决策和规划

- OS 支持已覆盖可按 UID 判定的 HoYoLAB/MYS 路由；Public data、BBS coin、QR login、device login 仍保持 CN-only，直到确认对应 OS 上游接口。
- Keyring 强制要求使用，坚决不引入明文保存密钥的回退方案。
- 图像渲染方面不断优化对齐 GenshinUID。
- 对于自动化和Agent的支持是最优先级的考虑；目前无需搭建 MCP 服务器（直接把此 CLI 作为 MCP 工具调用即可）。
