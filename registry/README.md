# 作品目录与离线准入校验

`index.json` 是当前本地基础目录，不是自动安装商店、托管分发服务或活跃社区市场。创作工坊的只读目录浏览器和 `GET /api/creators/registry` 暴露同一元数据供发现；不会访问下载 URL 或安装代码。索引记录作品身份、精确版本／散列、宿主与规则兼容范围、内容提醒、作者／许可、维护状态及证据链接；目录更新不会升级既有房间。

API 另返回按当前运行源码计算的静态兼容性：插件核对最低宿主版本及 Plugin API；预设核对最低宿主、Plugin API 和规则实现版本。最低宿主按数字基版比较，不区分 beta／预发行标签。插件 `requires` 未列入本目录的模块会单独提示，预设模块锁数量也会展示。**本机插件是否已安装、是否获信任／能力授权、下载包是否可用以及作品是否实际可运行都没有检查**；前端明确提示这一边界，不将静态条件说成安装或安全结论。

## 本地验证

```bash
python scripts/creator.py schemas --check
python scripts/registry.py
```

`registry/registry-index.schema.json` 是目录索引本身的版本化结构合同；其余九份内容、玩法、规则状态及插件清单 Schema 也通过 Creator CLI 生成。总计 **十个** Schema：五个内容／预设、三个核心状态／规则命令、一个插件清单、一个目录索引。JSON Schema 只描述结构；CLI 校验还会比对索引和真实清单、预设精确依赖锁与 package hash、ZIP SHA-256／入口和模板路径。

校验仅读取本地数据，不访问网络、不提取 ZIP 到磁盘，也不导入或运行插件 Python／JavaScript。成功结果中的 `code_executed: false`、`network_access: false` 是流程边界，不代表插件经过安全审计。校验不会检查在线 URL 当前是否可下载，也不会认证作者、许可证真实性或试玩质量。

## 状态与发布语义

- `source-template-not-published`：仓库内脚手架，不代表发行下载。
- `legacy-reference-only`：保留历史下载引用；远程内容未经此次联网核验、未声明分发许可的历史条目不作为推荐。
- `experimental-playable-vertical-sample` / `original-playtest-example`：示例或有限范围样板，不代表成熟市场作品、完整规则实现或第三方试玩。
- `community-submitted`：已准入元数据的社区投稿，不等于试玩。
- `community-playtested`：必须有明确作者／许可及可审阅试玩证据。
- `official-recommended`：必须有明确作者／许可、证据并经过项目维护者审核。
- `incompatible` / `archived`：保留状态信息，不自动安装，也不静默移除旧房间已锁定内容。

SHA-256 只证明字节完整性，不证明作者身份、来源、授权或安全。插件发行包在仓库 `plugin-packages/` 下时，离线校验会复核 ZIP 与清单；预设的 `download_url`／`archive_sha256` 目前只是发行元数据，CI 不联网取回归档，所以不能宣称远程预设包哈希已独立核验。社区投稿要求明确作者／许可及公开源码或维护联系入口；社区试玩／推荐另要求可审阅证据。许可待定的样板保持 `UNLICENSED` 且没有公开下载 URL。

## 投稿、兼容报告与维护

- 玩法作品投稿：GitHub Issue → `玩法作品投稿`。给出源码／精确版本、作者与再分发许可、兼容锁、内容提醒和真实测试范围。
- 兼容性／升级报告：GitHub Issue → `兼容性／升级报告`。提供宿主／规则／模块精确版本、package hash、最小复现；请先脱敏。
- 更新、停滞、归档／下架和许可更正：GitHub Issue → `目录维护／状态更正`。状态变更经审核后通过 PR 修改索引，并保留旧房间锁定行为。
- 代码模块仍按插件提案与独立代码审阅流程；数据预设导入不安装／信任代码。

作者提交时按 [PRESET_AUTHORING.md](../docs/PRESET_AUTHORING.md) 使用 `scripts/creator.py` 做 validate／lock／package；也可从作者仓库调用 `.github/workflows/community-validate.yml` 及对应的 preset／plugin release workflow。调用方必须将 reusable workflow 与 `sdk_ref` 都固定到经审阅的 40 位 Ember-Tavern commit SHA，不能引用分支或可移动 tag。Workflow 发布 Release ZIP 与实际 SHA-256 **不会自动更新中央索引**；之后还需按投稿表单另提目录更新 PR。索引变更需经过 `python scripts/registry.py`、Schema 漂移检查及 CI。自动化不替代作者／许可核实、代码审阅或真人验收；具体可复制示例见 [创作者指南](../docs/CREATOR_GUIDE.md)。

## 当前目录事实

- `index.json` 当前为本地基础目录：含四个插件条目和五个本机预设。两个历史插件资产的本地 ZIP SHA 已核验，但 URL 未重新联网核实，许可仍未声明；另两个仅为源模板。五个预设均为本机源目录，均没有公开下载归档；示例内容当前 `UNLICENSED`，不宣称获得社区再分发许可。
- 当前没有声称三位非核心作者已发布作品、社区试玩人数或独立第三方验收。M4 最终门槛尚未满足；真实朋友／环境测试按要求等 M4 完成后再安排。
- 后续版本兼容矩阵、签名、撤销清单、素材逐项 provenance、实际作者及归档 URL 的可用性核验仍待补齐。
