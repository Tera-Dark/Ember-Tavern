# M4 社区生态闭环：进行中

**状态：未完成。** 本文只记录第一批工程基底，不代表市场、分发或真人验收已经完成。

## 本轮交付（2026-10-04）

- 新增版本化目录索引合同 `server/contracts/registry.py`，纳入 Creator 共享 Schema；目录项包含作者／许可、维护状态、证据、宿主／Plugin API／规则版本、插件 `requires`／`provides`、精确预设插件依赖、包 SHA 与内容提醒等兼容和发现字段。只读 `GET /api/creators/registry` 暴露本地索引及静态兼容结果：按宿主数字基版（beta 标签不参与比较）核对最低宿主、Plugin API 和预设规则实现；本机插件安装／授权状态保持显式“未检查”。
- 补上离线准入 CLI：`python scripts/registry.py`。校验目录路径／符号链接边界、模板身份与兼容摘要、预设锁定 `package_hash` 和精确插件 pin、插件 ZIP SHA／清单／入口，以及索引中 Schema／模板内容与版本化合同的一致性。校验不联网、不解压到磁盘、不导入或执行第三方代码；它不等于代码安全审计、许可证认证、在线下载检查或真人试玩。
- 创作工坊新增只读目录浏览器：搜索、类型／审核状态筛选、来源／证据／维护／许可和内容提醒；静态宿主／API／规则兼容单独显示，不提供自动下载／安装，也不声称安装状态或代码安全。
- 新增社区作者可复用的验证、预设 Release、插件 Release workflow；工作流／SDK 均要求不可变 40 位 commit SHA，Release tag 需指向本次源码 commit；归档附实际 SHA-256。Release 不会自动修改中央目录，须另提经审查的索引 PR。
- CI 在单元测试前运行 Schema 漂移检查与目录校验；回归测试覆盖路径／哈希及试玩分级门槛、后端代码只作数据读取，并检查社区工作流 YAML、内嵌 Bash 语法、Action commit SHA 与作者指南样例。
- 新增 GitHub 表单：玩法作品投稿、兼容性／升级报告、目录维护／状态更正；PR 模板增加署名／许可、证据、版本锁、目录校验和旧房间不变检查项。
- 更正 Schema 数量与目录说明：总计十份生成 Schema（五份内容／预设、三份核心状态／规则命令、一份插件清单、一份目录索引）。

## 目录现状与明确限制

- `registry/index.json` 仍是**本地基础目录**，不是在线市场或自动安装源。当前有四个插件条目和五个本机预设条目。离线校验只复核仓库本地插件 ZIP；预设发行 URL／归档 SHA 字段若未来填写，仍须在具备网络访问的独立发布步骤中核验，不能视为此次 CI 验证。
- 两个历史插件包的本地 ZIP SHA 已核对；历史下载 URL 未联网复核且发行许可未声明，仅保留为 `legacy-reference-only`，不作为新推荐。另两个插件只有本地源码模板。五个预设目前都没有公开下载归档；现有样板为 `UNLICENSED`，不声称已获再分发授权。
- 目前没有证据证明三位非核心作者制作并发布了不同的可玩作品；也没有完成“独立第三方模块不改宿主代码”的社区实证。不得把官方模板、示例创作者署名或自动测试伪装成这类验收。
- 目录 UI 与 GitHub 发布自动化仅是只读发现／作者工具，不是在线市场；尚无签名／撤销、在线 URL 可用性监控、完整 provenance、长期维护轮值。工作流没有在独立社区作者仓库由非核心作者实际执行；现有创作 CLI 直接从固定仓库 commit 提供，尚未成为独立版本化 SDK 分发物。
- 仓库正式代码／内容许可证、示例再分发权和公开下载版本落后于源码的问题仍未解决；本轮没有改动 Release，也没有擅自公开发布。

## 最终验收（全部仍开放）

1. 至少 3 位**非核心作者**制作并发布不同的可玩作品；逐项记录作者、授权、下载／源码、精确 hash、宿主兼容与真实试玩证据。
2. 至少 1 个独立作者模块通过正式插件契约，无需修改宿主源码即可安装、运行、关闭与升级；运行任意 Python 代码仍需明确的部署者信任与审查，不能宣传为沙箱。
3. 目录、作品、依赖和规则升级不改变既有房间已经锁定的版本／散列；用升级前后快照和明确版本进行回归验证。当前自动化已有 `tests/test_presets.py::test_rule_and_plugin_changes_do_not_silently_upgrade_campaign` 并包含在本轮 192 项通过中，但实际已发布版本之间的升级验证仍未完成。
4. 创作者 SDK／文档、投稿、兼容报告、维护／归档／许可更正流程在 CI 和实际贡献路径中可用；未知作品不自动安装或执行。

按明确约束，**朋友／真实环境测试只在上述 M4 工作完成后安排**；目前未安排，也未声称通过。自动测试不替代作者身份／版权审阅或真人试玩。

## 本轮验证

- `.venv/bin/python scripts/creator.py schemas` 与 `schemas --check`：通过，重新生成的目录 Schema 无漂移。
- `.venv/bin/python scripts/registry.py`：通过，检查 4 个插件和 5 个预设；对 2 个历史远程下载引用输出“不联网验证”的警告。
- `pytest tests/test_registry.py -q`：10 项通过；新增 `pytest tests/test_community_workflows.py -q`：7 项通过；全后端 `pytest -q`：**199 passed, 2 warnings**（Starlette/httpx 弃用提示及既有重复 ZIP 测试警告）。
- `.venv/bin/python -m compileall -q server plugins scripts templates tests`、社区 workflow／Issue Form YAML 与内嵌 shell 语法检查、`git diff --check`：均通过。
- `cd web && npm ci && npm run build`：通过；重复构建前后 `static/` 内容 hash 相同，npm 报告 0 vulnerabilities。
- 本机只有 Python 3.11，未跑 CI 的 Python 3.13 矩阵；Playwright Chromium 未安装，受此前下载 TLS 限制，本轮未运行浏览器 E2E。GitHub reusable workflow 未在外部作者仓库实际调用，也未创建社区 Release；没有朋友／真实环境测试，不能用自动化结果冒充这些验收。
