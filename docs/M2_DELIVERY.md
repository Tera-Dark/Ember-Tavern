# M2 工程切片：战役状态、来源记忆与多人行动

**更新：2026-10-03。状态：源码分支已实现 M2 服务端和网页工作台，自动化回归通过；不是新 Release，也不是 M2 最终人工验收报告。**

## 版本和公开下载状态

| 对象 | 当前源码元数据 | 公开下载 / 证据 |
| --- | --- | --- |
| 宿主 / 网页 | `2.4.0-beta.1` | 最新可见桌面 Release 仍是 `0.2.0-beta.1` / 旧宿主 `2.3.0-beta.1`；没有本轮 M2 EXE |
| 桌面 / 部署引擎 | `0.2.0-beta.3` | 新 Release 尚未发布，不能把源码版本号当作公开下载版本 |
| Plugin API | `1` | M2 未升级插件主版本 |
| 核心存档 | `schema_version=3` | 从此前状态迁移；旧 `ember.preset/v1`、`ember.scenario/v1` 契约不变 |
| 战役状态 | `ember.campaign-state/v1` | 新增独立 JSON Schema：`registry/campaign-state.schema.json` |
| 规则适配器 | `ember-light/v1`，实现 `1.1.0` | 仍只有轻规则，没有增加 5e 或 SLG 规则 |

公开 Release 的 dispatch 曾返回 GitHub `403 Resource not accessible by integration`；尝试读取 Windows artifact 时签名下载返回 `EOF`。因此没有可核验的新 EXE、构建来源清单或新 Release。不要用旧 Release 验收 M2；公开下载落后源码的问题**尚未解决**，需先修复仓库工作流权限并从明确提交构建、校验、发布。

## 已实现的 M2 能力

### 1. 有界战役 Ledger

- 任务、NPC、资源为 Pydantic 强类型记录；每类最多 64 条，总计最多 120 条；ID 唯一；NPC 关系限制为 −5…5；资源必须满足 `minimum ≤ value ≤ maximum`。
- 支持 `public` 与 `gm` 可见性；服务器分别生成房主 / 玩家投影。房主从网页「战役状态」维护进度、关系和数值，并通过事件快照回档。
- 新增宿主 API：`GET/PUT /api/rooms/{room_id}/campaign-state`。修改仅限房主，并校验 `expected_revision`、`branch` 和 `request_key`。
- 新增只读插件资源 `core.campaign-state/v1`（能力 `read:room`），只提供公共 Ledger、行动模式和公开行动轮次。
- 这是固定任务／NPC／资源契约，不是任意字段 DSL，不提供 eval 或任意 JSON Patch。叙事 AI 不直接写数值；严格战斗和经济仍需规则适配器。

### 2. 多人行动收集

- 行动模式为 `free`（现有立即处理流程）和 `round`（各受分配角色提交一次，房主手动结算）。
- 新增 `PUT /api/rooms/{room_id}/action-mode`、`POST /api/rooms/{room_id}/action-round/settle`；轮次记录包含分支、参与角色、提交状态、缺席角色和行动正文。
- 收集期间不自动调用主持，也不自动替未提交玩家行动；房主可等待全员或明确提前结算。结算后仍走现有权威主持、检定与状态校验流程。
- 请求回执可避免重复提交／结算；重复角色、过期修订和旧分支均拒绝。回档清除分支绑定轮次。

### 3. 带来源的主持记忆

- 房主手动编辑摘要，必须绑定 1–50 条同房间、当前 active、非摘要自身的事件；摘要上限 4000 字符。
- 新增房主专属 `GET /api/rooms/{room_id}/memory` 和 `PUT /api/rooms/{room_id}/memory/summary`。玩家投影、普通插件核心资源和普通事件投影不包含摘要正文或来源列表。
- 模型上下文默认最多使用 3000 字符，可由 `MEMORY_SUMMARY_CONTEXT_CHARS` 配置，代码上限 8000 字，并继续受总上下文预算约束。追踪信息仅给房主查看，不把完整 prompt 暴露给玩家。
- 回档会清除摘要；封存事件、其他房间事件、旧分支来源不能成为当前摘要来源。摘要是房主审阅的辅助记忆，不是权威正史，也不是自动生成／无限记忆。

### 4. 审阅规则目录与存档迁移

- 新增只读 `GET /api/rules`。注册表仅允许经审阅的宿主代码注册；每个适配器要提供版本化 ID、实现版本、SHA256、结构化检定 / 决策 Schema。
- 已核验 `LightRules.contract()` 同时包含上述字段；未知规则 ID 返回错误，不会因为世界书文字或插件内容而启用。
- 核心状态推进到 `schema_version=3`；旧状态迁移补入空 Ledger、`free` 模式、空轮次和空记忆。当前版本读取保持幂等；不支持的未来版本明确拒绝。
- 生成并通过检查 `registry/campaign-state.schema.json`。`core.*` 插件资源不能由普通插件提供或覆盖。

## 新增 / 变更接口摘要

| 方法 | 路径 | 权限 / 重点 |
| --- | --- | --- |
| `GET` | `/api/rules` | 公开只读已审阅规则适配器目录 |
| `GET` / `PUT` | `/api/rooms/{id}/campaign-state` | 房间成员读取；仅房主修改 Ledger |
| `PUT` | `/api/rooms/{id}/action-mode` | 仅房主；`mode`=`free` 或 `round` |
| `POST` | `/api/rooms/{id}/action-round/settle` | 仅房主；`branch` 与 `expected_revision` 必填 |
| `GET` | `/api/rooms/{id}/memory` | 仅房主；返回当前来源事件与摘要 |
| `PUT` | `/api/rooms/{id}/memory/summary` | 仅房主；非空摘要必须附当前有效来源 |

除规则目录外，写操作使用现有 `request_key` 幂等回执。房间状态写请求同时校验 revision 和 branch；错误请求不会写入快照。

## 自动化验证与剩余验收

当前源码分支验证记录（2026-10-03）：

- 后端全套：`.venv/bin/python -m pytest -q` → **169 passed, 2 warnings in 28.57s**。警告分别是 Starlette 对 `httpx` 的弃用提示，以及恶意 ZIP 测试刻意构造重复文件名时 `zipfile` 的提示。测试覆盖 3 个房间、60 次确定性行动的 Ledger 保持，轮次权限／幂等／提前结算、私密投影、记忆来源／回档、未知规则与 schema v2→v3 迁移。60 次测试使用本地确定性主持桩并跳过每分钟 12 次的行动限速，只验证服务端状态完整性，**不证明语言模型事实准确性、限速行为或互联网性能**。
- 前端生产构建：`npm run build`（`web/`）→ Vite 6.4.3，1588 modules；构建输出同步到仓库已有 `static/` 部署目录。
- 创作 Schema：`.venv/bin/python scripts/creator.py schemas --check` → `schema_drift: []`、`generated: []`。

仍未关闭：

1. `M2` 不等于新的规则玩法：没有实现 D&D/5e SRD 子集、CoC、SLG-lite，也没有宣称支持完整商业规则。
2. 人工 / 供应商模型的关键事实准确率尚未测量；60 次是确定性 API 状态保持，不是人工评分或真实模型评测。
3. 真实朋友、LAN / 外网和真实模型环境测试严格延后到 **M4 完成后**；当前不安排、不宣称完成人测。
4. 公开下载版本落后源码问题仍待 CI 权限、可下载 Windows 产物和新 Release 修复；不以本地构建代替公开发布。

## 复现

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/creator.py schemas --check
npm ci --prefix web
npm run build --prefix web
```

这些是源码 / 自动化测试步骤，不是 Windows 原生打包、公开发布或 M4 真人测试证据。
