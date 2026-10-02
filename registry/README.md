# 本地创作与插件契约索引

`index.json` 是本地基础目录，不是自动安装商店或活跃用户市场。

- content_templates 指向实际 worldbook／character／theme 模板及对应 Schema；gameplay_templates 指向 preset / scenario，CLI 另有 plugin-campaign 只读样板。
- 六个 `*.schema.json` 来自 `server/contracts/`，CLI／运行时／安装器共用。`python scripts/creator.py schemas --check` 检查漂移；审阅后才能生成更新，别直接手改 JSON。
- JSON Schema 是结构提示；总字节、hp≤max_hp、唯一 ID、已安装版本／信任等以官方运行时为准。
- session-insights／scene-notes 的既有发行 URL 保留历史引用，本轮只核验仓库内 ZIP 的真实 SHA，未重新验证远程下载；dice-tray 只有源模板，URL／SHA 留空，不能写成已发布。
- 真实 Release 发布后，填对应 HTTPS URL 与**实际 ZIP** SHA；保留 API、minimum_host、能力、backend、审阅状态、作者／许可信息。源码审核、作者身份、签名和许可证不由 hash 自动证明。

后续版本兼容矩阵、签名、撤销清单与逐条素材 provenance 见 ROADMAP；当前不自动拉取／执行第三方 Python。

M1 作者指南：[PRESET_AUTHORING.md](../docs/PRESET_AUTHORING.md)。原生数据预设与独立代码插件分开打包 / 审阅。`preset_library` 是源码样板，URL 留空；UNLICENSED 表示正式再分发许可待定，不是认证商城。
