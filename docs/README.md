# 文档入口

## 当前源码状态（2026-10-12）

2026-10-12 增量：桌面 / 部署引擎源码 `0.2.0-beta.4`，[更新与版本管理](UPDATE_GUIDE.md)、[独立作者 SDK 0.2.0](AUTHOR_SDK.md) 和[投稿 / 核验 / 目录维护](COMMUNITY_REVIEW.md) 已有本地实现 / 验证；[M4 最新进度](M4_DELIVERY.md) 仍为未完成。后端最终 261 项回归通过，尚未发布对应公开包。下列 2026-10-03 版本对照保留为历史快照。

- [M2 状态 / 记忆 / 多人行动](M2_DELIVERY.md)：源码切片、自动化回归和未关闭边界。
- [M3 玩法竖向样板](M3_DELIVERY.md)：SRD 5.2.1 有限战斗与原创合作 SLG-lite；专项／完整后端测试、Schema、构建结果和许可／发布边界。不是完整 5e / SLG、已发布二进制或真人验收。
- [M4 社区生态闭环（进行中）](M4_DELIVERY.md)：目录契约／离线校验、CI 与投稿／兼容／维护入口的第一批基底；不代表社区、发布或真人验收完成。
- [M1 数据玩法组合与剧本交付](M1_DELIVERY.md) · [世界／剧本／预设作者实战](PRESET_AUTHORING.md) · [格式设计决策](PRESET_FORMAT_RFC.md)
- [M0 第一批交付 / 新手开桌 / 恢复与发布](M0_DELIVERY.md)：2026-10-02 阶段快照，宿主 2.3.0-beta.2、桌面 / 引擎 0.2.0-beta.2；是开发记录，不代表该版本已公开下载。
- 版本对照：当前宿主 / 网页 2.4.0-beta.1、桌面 / 引擎 0.2.0-beta.4、SDK 0.2.0；最新公开桌面为 beta.3 / 宿主 2.4.0-beta.1。本次更新底座与 SDK 尚未公开发行。拥有者已授权外部试用，见 [源码试用](SNAPSHOT_TESTING.md)。

- [桌面完整体验计划](DESKTOP_EXPERIENCE_PLAN.md) · [状态矩阵](DESKTOP_EXPERIENCE_STATE_MATRIX.md) · [执行记录](DESKTOP_EXPERIENCE_PROGRESS.md)：完整 A–F 仍在实施，区分本地代码验证与真实安装包 / 外部反馈。

## 当前计划与长期约束

- [下一阶段开发计划](DEVELOPMENT_PLAN.md)：2026-10-12 状态入口；区分源码、公开下载、M2 自动验收、M3/M4 与真人测试门槛。
- [核心需求](CORE_REQUIREMENTS.md)：后续设计 / PR 应持续遵守的用户要求。
- [需求调研](AI_RPG_DEMAND_RESEARCH.md)：公开证据、不能推出的结论和试玩验证方案；不是热度排名。

## 玩家与房主

1. [快速启动](../QUICKSTART.md)
2. [桌面房主指南](DESKTOP_GUIDE.md)
3. [游戏指南](PLAY_GUIDE.md)
4. [LAN / 代理 / 备份](LAN_DEPLOYMENT.md)
5. [桌面验收与边界](DESKTOP_TEST_REPORT.md)

## 世界书 / 角色 / 主题作者

1. [创作指南与现有脚手架](CREATOR_GUIDE.md)
2. [模板说明](../templates/README.md)
3. [格式与 schema](../registry/README.md)
4. [GitHub 发布](GITHUB_PUBLISH.md)
5. [独立作者 SDK 与统一发布检查](AUTHOR_SDK.md)
6. [作品投稿、发行核验与目录维护](COMMUNITY_REVIEW.md)

M1 数据型剧本 / 玩法组合与 M3 两条实验规则预设均已进入当前源码。M3 的有限规则范围、测试结果与不支持项见 [M3 交付记录](M3_DELIVERY.md)；不代表完整 5e / SLG。2026-10-12 拥有者已授权他人试用当前源码；M4 保持进行中，实际反馈仍待取得。

## 插件与宿主开发者

1. [Plugin SDK v1](PLUGIN_SDK.md)
2. [架构与权限边界](ARCHITECTURE.md)
3. [贡献指南](../CONTRIBUTING.md)
4. [安全](../SECURITY.md)
5. [测试报告](TEST_REPORT.md)

架构 / SDK / 测试 / M0 / M1 报告保留各自时间点的版本快照；标题里的旧版本不表示当前下载内容。当前代码功能以源码契约和 [M2 交付记录](M2_DELIVERY.md) 为准；当前已公开 EXE 为 beta.3，本次 beta.4 尚未发行，不能拿文档版本号证明已发布。`archive/` 是历史，不是当前使用入口。
