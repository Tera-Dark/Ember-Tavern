# 本次源码试用（2026-10-12）

仓库拥有者已授权把当前源码更新到 GitHub，供他人下载试用。M4 保持进行中，试用反馈不等于正式生态验收通过。源码版本：宿主 / 网页 `2.4.0-beta.1`，桌面 / 引擎 `0.2.0-beta.4`，作者 SDK `0.2.0`。

## 获取与运行

在 [main 源码](https://github.com/Tera-Dark/Ember-Tavern/tree/main) 点 Code → Download ZIP，或 `git clone https://github.com/Tera-Dark/Ember-Tavern.git`。若已经下载旧源码，先记录版本并备份，使用新目录进行首次试用。

Windows PowerShell（Python 3.11+）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 65536
```

仅在新目录、尚无 `.env` 时执行复制。macOS / Linux 启动命令见 [快速启动](../QUICKSTART.md)。附带 `static/`，运行游戏无需 Node。房主打开 `http://localhost:8000`；同伴用浏览器访问同一服务器的 LAN 地址。首次使用演示模式和临时测试账号，无需模型密钥。

最新已公开桌面 Release 是 [beta.3](https://github.com/Tera-Dark/Ember-Tavern/releases/tag/desktop-v0.2.0-beta.3)，它没有本次 beta.4 的更新底座。检查桌面版本页与点击更新需要从本次提交构建 beta.4；普通 CI 的 Windows 构建产物可在对应 Actions 的 `ember-desktop-windows-x64` Artifact 中取得，须先查看该次检查是否全部成功。Artifact 是测试构建，不是新公开 Release。早期安装包不会因 main 更新而自动获得新版桌面功能。

## 建议检查

1. 游戏：开桌、同伴入座、分配角色、同步行动、地图移动、关闭 / 重启和剧情回档；核对玩家只能读取自己的公开视图。
2. 桌面 beta.4：检查 GitHub、显示历史版本、失败时保留原版；实际更新 / 降级使用独立测试实例，先阅读 [更新与数据快照语义](UPDATE_GUIDE.md)。尚无更新的 beta.4 公开发行时，不应预期下载到不存在的版本。
3. 作者工具：生成模板、校验、锁定预设、打包；按 [作者 SDK](AUTHOR_SDK.md) 和 [投稿流程](COMMUNITY_REVIEW.md) 操作。模拟 / 未公开作品不能声称线上核验成功。
4. 反馈：提供源码 commit、系统 / 浏览器、操作步骤、预期与实际结果、脱敏错误截图或日志。使用仓库 Bug / 兼容性 Issue 表单；不要附密钥、`.env`、账号库或完整备份。

当前没有供应商费用硬额度，真实模型与 TTS 调用由测试者自行配置并控制预算。个人 API 配置未进入仓库、构建产物或 CI。

## 提交前验证

本机后端 261 项、桌面 32 项测试通过；Go 测试 / vet、Schema / 目录校验、网页与桌面构建、原生更新辅助程序及模拟发行的原生界面测试通过。网页重建没有改变 `static/`。实际 GitHub CI 结果以当前提交的 Actions 为准。

网页依赖审计与桌面运行依赖审计均为零；桌面打包工具链仍有 8 项中等告警，来自尚无兼容修复版的 [sprintf-js 及依赖链](https://github.com/advisories/GHSA-hp3w-g68c-fv3c)。已更新可兼容修复的 source-map-js / http-cache-semantics，没有强制降级打包工具来掩盖告警。
