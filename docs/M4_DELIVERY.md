# M4 社区生态闭环：进行中

**状态：未完成。** 目录基础、作者 SDK 和创作发布工程已有增量；公开发行、授权与独立作者验收仍开放。

## 本轮推进（2026-10-12）

- 桌面 / 部署引擎更新底座已进入 `0.2.0-beta.4` 源码和本地开发包，支持 GitHub 检查、点击更新、历史版本切换、回退提示抑制与本体数据快照。详见 [更新指南](UPDATE_GUIDE.md) 和 [更新验证记录](UPDATE_TEST_REPORT.md)。未发布新的公开桌面 Release。
- 独立作者 SDK 从首批 `0.1.0` 扩展至 `0.2.0`：`author-sdk.json`、`scripts/author_sdk.py`。生成版本根目录 ZIP、逐文件清单、整包 SHA256、宿主 / Plugin API / Python 兼容信息、精确来源 commit 与 dirty 状态；同一源码状态构建可复现。只读验证检查路径、大小、重复 / 大小写冲突、链接、额外文件与散列，不解压或运行作品代码。
- SDK 可在仓库外单独使用：无需完整宿主 Git checkout、Node、Go、Electron；模板创建、Schema 检查、内容 / 插件校验、预设锁、ZIP 打包及锁定投稿生成均已用独立目录验证。包内入口为 `ember-creator.py`、`ember-plugins.py`、`ember-community.py`，使用自带锁定 Python 依赖。详见 [作者 SDK](AUTHOR_SDK.md)。这是本地开发包，未成为公开 Release 或 PyPI 分发。
- 新增统一 `creator.py release-check`，本地作者与社区预设 / 插件发布工作流共享署名、许可、全部预设组件、精确内容锁和 tag 检查。检查不认证作者身份或权属，也不执行作品代码。
- 新增 SDK 不可变发布工作流和核心 CI 开发包产物。公开模式要求干净提交、真正的 `LICENSE` 与明确覆盖 SDK 代码 / 模板 / 文档的 `AUTHOR_SDK_LICENSE.md`；这些正式许可仍待拥有者确定。发布 tag 必须对应构建提交，拒绝替换已有 SDK Release 资产。本轮未调用发布工作流。
- 作者 CLI 使用纯文件散列 helper，避免导入游戏插件运行时；运行时保留原兼容导出，散列算法 / 审核锁没有变更。本机部分文件只有换行字节偏差，已核对 Git 原文并恢复一致；内置插件的原审核锁全部匹配，没有运行 lock-builtins。
- 新增 `community.py` 的来源声明、投稿生成、GitHub 发行核验、审核 / 拒绝、目录 PR 暂存与版本维护命令；共享三个新契约，Schema 总数十三。Release 工作流附来源声明，锁定作品 / SDK commit 与实际 ZIP。审核暂存保留原索引、旧版本和房间锁，不执行作品代码、不自动推荐或安装；审核补丁保存原投稿 / 来源声明 / 核验与审核记录，便于归档后追溯。详见 [投稿与维护流程](COMMUNITY_REVIEW.md)。
- 最新全后端回归 **261 passed, 1 warning**（既有重复 ZIP 防护 fixture 提示）；Schema 无漂移、4 个插件 / 5 个预设的离线目录校验、真实 Git Bash 的工作流语法检查、Issue Form YAML、独立 SDK 工具链测试及 `git diff --check` 通过。线上核验使用模拟 GitHub 传输检查 tag / commit / 缺失或重复资产 / ZIP / 来源错配、重定向与大小限制，未冒充真实公开发行验收。未用私有 API 发起付费生成、未进行朋友 / 用户真实数据验收。
- 本地开发包 `artifacts/author-sdk/0.2.0/ember-author-sdk-0.2.0.zip`（139 个文件）及 SHA256 已构建和独立校验；SHA256 为 `e6c2c5a0f70ac605f08324addaa1685411b54ffa2c24c45a73c29ac6d967a40d`。清单明确 `source_dirty: true`、`publication_ready: false`，没有公开发布。

### 仍需推进的清单

| 项目 | 当前状态 | 完成条件 |
| --- | --- | --- |
| 作者 SDK / 本地创作发布工具 | 本地工程与隔离回归已落地 | 明确许可、干净提交、SDK 不可变公开发行，并在外部作者仓库实际使用 |
| 桌面 / 本体更新 | 源码与本地包已验证 | 可追溯的公开桌面发行；实际已发布版本之间的下载、升级与旧房间验证 |
| 投稿 / 目录 / 维护 | 投稿、核验、审核暂存与版本维护工具已通过模拟 / 本地回归 | 实际作品投稿、真实公开资产 / 来源核验、兼容 / 下架 / 维护流程实际执行 |
| 第三方作品与模块 | 最终验收仍缺证据 | 至少三位非核心作者的不同可玩作品，以及至少一个独立作者模块，无需修改宿主代码 |
| 正式许可 | 未决定 | 拥有者明确代码、原创内容、SDK 样板与第三方材料的授权边界 |

这些本地工程增量没有改变 M4 原定验收标准；下方四项最终验收仍未关闭。官方模板和本轮合成测试作者不计作独立作者。

## 本轮交付（2026-10-04）

- 新增版本化目录索引合同 `server/contracts/registry.py`，纳入 Creator 共享 Schema；目录项包含作者／许可、维护状态、证据、宿主／Plugin API／规则版本、插件 `requires`／`provides`、精确预设插件依赖、包 SHA 与内容提醒等兼容和发现字段。只读 `GET /api/creators/registry` 暴露本地索引及静态兼容结果：按宿主数字基版（beta 标签不参与比较）核对最低宿主、Plugin API 和预设规则实现；本机插件安装／授权状态保持显式“未检查”。
- 补上离线准入 CLI：`python scripts/registry.py`。校验目录路径／符号链接边界、模板身份与兼容摘要、预设锁定 `package_hash` 和精确插件 pin、插件 ZIP SHA／清单／入口，以及索引中 Schema／模板内容与版本化合同的一致性。校验不联网、不解压到磁盘、不导入或执行第三方代码；它不等于代码安全审计、许可证认证、在线下载检查或真人试玩。
- 创作工坊新增只读目录浏览器：搜索、类型／审核状态筛选、来源／证据／维护／许可和内容提醒；静态宿主／API／规则兼容单独显示，不提供自动下载／安装，也不声称安装状态或代码安全。
- 新增社区作者可复用的验证、预设 Release、插件 Release workflow；工作流／SDK 均要求不可变 40 位 commit SHA，Release tag 需指向本次源码 commit；归档附实际 SHA-256。Release 不会自动修改中央目录，须另提经审查的索引 PR。
- CI 在单元测试前运行 Schema 漂移检查与目录校验；回归测试覆盖路径／哈希及试玩分级门槛、后端代码只作数据读取，并检查社区工作流 YAML、内嵌 Bash 语法、Action commit SHA 与作者指南样例。
- 新增 GitHub 表单：玩法作品投稿、兼容性／升级报告、目录维护／状态更正；PR 模板增加署名／许可、证据、版本锁、目录校验和旧房间不变检查项。
- 更正 Schema 数量与目录说明：总计十份生成 Schema（五份内容／预设、三份核心状态／规则命令、一份插件清单、一份目录索引）。

桌面作者工作区及社区模块版本事务已有后续本机工程：模板 / 元数据 / 校验 / 新版本包 / 发布前检查，以及停服 / 完整备份 / 副本迁移 / 模块数据回退。具体证据和保护边界见 [桌面执行记录](DESKTOP_EXPERIENCE_PROGRESS.md)。它们不替代下列独立作者公开作品与真实贡献路径验收。

## 目录现状与明确限制

- `registry/index.json` 仍是**本地基础目录**，不是在线市场或自动安装源。当前有四个插件条目和五个本机预设条目。离线校验只复核仓库本地插件 ZIP；预设发行 URL／归档 SHA 字段若未来填写，仍须在具备网络访问的独立发布步骤中核验，不能视为此次 CI 验证。
- 两个历史插件包的本地 ZIP SHA 已核对；历史下载 URL 未联网复核且发行许可未声明，仅保留为 `legacy-reference-only`，不作为新推荐。另两个插件只有本地源码模板。五个预设目前都没有公开下载归档；现有样板为 `UNLICENSED`，不声称已获再分发授权。
- 目前没有证据证明三位非核心作者制作并发布了不同的可玩作品；也没有完成“独立第三方模块不改宿主代码”的社区实证。不得把官方模板、示例创作者署名或自动测试伪装成这类验收。
- 目录 UI 与 GitHub 发布自动化仅是只读发现／作者工具，不是在线市场；尚无签名／撤销、在线 URL 可用性监控、逐项素材 provenance、长期维护轮值。包级来源声明和在线核验已有实现，但未取得真实社区发行验收。工作流没有在独立社区作者仓库由非核心作者实际执行；版本化 SDK 已有本地 ZIP / 校验 / 发布工程，但正式许可和独立公开分发仍未完成。
- 仓库正式代码／内容许可证、示例再分发权和公开下载版本落后于源码的问题仍未解决；本轮没有改动 Release，也没有擅自公开发布。

## 最终验收（全部仍开放）

1. 至少 3 位**非核心作者**制作并发布不同的可玩作品；逐项记录作者、授权、下载／源码、精确 hash、宿主兼容与真实试玩证据。
2. 至少 1 个独立作者模块通过正式插件契约，无需修改宿主源码即可安装、运行、关闭与升级；运行任意 Python 代码仍需明确的部署者信任与审查，不能宣传为沙箱。
3. 目录、作品、依赖和规则升级不改变既有房间已经锁定的版本／散列；用升级前后快照和明确版本进行回归验证。当前自动化已有 `tests/test_presets.py::test_rule_and_plugin_changes_do_not_silently_upgrade_campaign` 并包含在本轮 192 项通过中，但实际已发布版本之间的升级验证仍未完成。
4. 创作者 SDK／文档、投稿、兼容报告、维护／归档／许可更正流程在 CI 和实际贡献路径中可用；未知作品不自动安装或执行。

2026-10-12 拥有者已更新安排：提交当前源码到 GitHub，允许他人下载试用。见 [源码试用](SNAPSHOT_TESTING.md)。目前没有实际试用反馈，不声称已经通过真人验收；自动测试不替代作者身份／版权审阅或真人试玩。

## 本轮验证

- `.venv/bin/python scripts/creator.py schemas` 与 `schemas --check`：通过，重新生成的目录 Schema 无漂移。
- `.venv/bin/python scripts/registry.py`：通过，检查 4 个插件和 5 个预设；对 2 个历史远程下载引用输出“不联网验证”的警告。
- `pytest tests/test_registry.py -q`：10 项通过；新增 `pytest tests/test_community_workflows.py -q`：7 项通过；全后端 `pytest -q`：**199 passed, 2 warnings**（Starlette/httpx 弃用提示及既有重复 ZIP 测试警告）。
- `.venv/bin/python -m compileall -q server plugins scripts templates tests`、社区 workflow／Issue Form YAML 与内嵌 shell 语法检查、`git diff --check`：均通过。
- `cd web && npm ci && npm run build`：通过；重复构建前后 `static/` 内容 hash 相同，npm 报告 0 vulnerabilities。
- 本机只有 Python 3.11，未跑 CI 的 Python 3.13 矩阵；Playwright Chromium 未安装，受此前下载 TLS 限制，本轮未运行浏览器 E2E。GitHub reusable workflow 未在外部作者仓库实际调用，也未创建社区 Release；没有朋友／真实环境测试，不能用自动化结果冒充这些验收。
