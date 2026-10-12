2026-10-12 公开资产核对：最新桌面 Release 为 `desktop-v0.2.0-beta.3`（宿主 2.4.0-beta.1），本次 beta.4 更新底座尚未公开发行。测试当前代码见 [源码试用](../docs/SNAPSHOT_TESTING.md)。后文标注 2026-10-03 的版本信息为历史记录。

# 余烬桌面

**更新底座（2026-10-12）：**当前桌面 / 部署引擎源码为 `0.2.0-beta.4`，新增 GitHub 自动检查、点击更新、历史版本切换、回退提示抑制和本体数据快照。使用与旧包迁移边界见 [更新指南](../docs/UPDATE_GUIDE.md)。这是源码 / 本地开发构建，尚未发布新的公开安装包。以下 2026-10-03 版本说明保留为历史记录。

房主专用 Electron + TypeScript + Vite + Vue 控制台，复用 Go 部署引擎和 Python / React 宿主。只有房主安装；同伴浏览器身份 + 密钥入座。

**版本状态（2026-10-03）：**当前源码元数据为桌面 / Go 部署引擎 `0.2.0-beta.3`、宿主 `2.4.0-beta.1`；最新公开 Windows Release 仍为 `desktop-v0.2.0-beta.1`（旧宿主 `2.3.0-beta.1`）。当前 M2 尚无已核验 EXE，不要用旧包验收 M2；详情见 [M2 交付记录](../docs/M2_DELIVERY.md)。

- [旧版 Windows x64 EXE / Release](https://github.com/Tera-Dark/Ember-Tavern/releases/tag/desktop-v0.2.0-beta.1)
- [安装、使用、LAN、安全与备份](../docs/DESKTOP_GUIDE.md)
- [历史验收记录与边界](../docs/DESKTOP_TEST_REPORT.md)

M1 源码切片提供选包开桌、来源锁、原生数据文件预览确认；规则 / 模块代码依赖不自动安装。阶段状态见 [M1 交付记录](../docs/M1_DELIVERY.md)，当前源码功能见 [M2 交付记录](../docs/M2_DELIVERY.md)。
