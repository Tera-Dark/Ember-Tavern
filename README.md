# 余烬酒馆 · 模块化多人跑团

**宿主 2.1.0-beta.2 测试版 · 启动器 0.1.0-beta.2 测试版 · Plugin API v1**

项目仓库：[Tera-Dark/Ember-Tavern](https://github.com/Tera-Dark/Ember-Tavern) · 第一次下载请先看 [快速启动指南](QUICKSTART.md)。

只运行不需要 Node，已包含构建前端。多人同桌需访问**同一个服务器**，不要每人各起一个实例再互发邀请码。

小宿主维护身份、房间、权限、通用轻规则、权威状态、事件与回档；地图、生成器、图标移动、旁白台本、TTS 和 AI 主持都是独立可开关模块。界面不是静态原型，实际操作会写数据库、同步到同伴并生成回档快照。

目前可演示／测试：双账号房间、分配角色、AI 演示主持、检定、属性、世界书、检索、分支回档、方格地图生成、多人拖动预览与提交、台本编辑、本地语音 SDK、社区插件安装／隔离。真实供应商联网与音频听感需要你在服务器配置自己的密钥；**不会让你把密钥发聊天。**

## 桌面启动器（Windows x64）

双击版本号命名的启动器 EXE，点「新建实例 → 创建并启动」。启动器自动准备 Python、下载项目并安装依赖；卡片右上可从固定 GitHub 仓库原地更新，备份并预检后替换，失败恢复旧代码 / 环境 / 数据。

账号、房间、素材和密钥独立保存在 `%LOCALAPPDATA%\EmberTavern`。不要求手动装 Python / Git / Node，不修改系统 PATH。

[启动器说明](launcher/README.md) · [验收边界](docs/LAUNCHER_TEST_REPORT.md)。Windows EXE 已构建；完整 Windows 桌面安装仍需实机验收。下载启动器版本对应的 Release，不要把旧应用源码包当成 EXE。

## 手动运行（开发 / 备用）

Python 3.13 为本次验证环境。无需 Node 即可运行附带的 static。

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-lock.txt
cp .env.example .env
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 65536
```

浏览器打开本机 `http://localhost:8000`。首次选择免费试玩无需 key；与朋友长期保存房间请分别注册正式账号。房主建房、给邀请码、在角色档案分配操控者，接着到「模块中心」按需启用地图／声音。

**单 worker 是当前架构要求**：SQLite WAL＋进程内 WS／锁。不要直接改 workers 为多进程；需先换共享消息与协调存储。对公网开放前审查 CORS／Origin、HTTPS、费用限额与备份；不是商业 SLA 的生产 VTT。

## 模块

| 插件 | 默认 | 用法 |
| --- | --- | --- |
| ai-host | 开 | 演示或真实双模型主持；可关闭，行动等待房主人工补述 |
| scene-map | 关 | 共享方格渲染；程序／社区发布的 scene.map/v1 |
| map-generator | 关 | 开启自动补 scene-map；4 地形和 seed；可选 AI 结构化布局 |
| map-tokens | 关 | 开启补 scene-map；房主全控、玩家仅自己，实时拖动预览 |
| narrator-script | 关 | 最近有效剧情分段、说话者、房主编辑／重建 |
| voice-tts | 关 | 开启补 narrator-script；浏览器朗读与外部保存音频 |

关闭保留数据；关底座会确认级联关依赖者。模块开关属于房间配置，不随剧情回档；地图／位置／台本／音频引用属于 namespace 快照，随剧情回档。没有完整路径、战棋先攻、视线或语音会议。

## 一分钟安装社区示例

```bash
# ZIP 与对应 SHA256 均已随发行包提供。
python scripts/plugins.py install plugin-packages/session-insights-1.0.0.zip --sha256 <同名.sha256文件中的值>
```

模块中心「刷新已安装清单」，开启「会话观察板」；独立导航自动出现，不改 App.jsx，不重新 build。只有 read:room/read:events，没 Python、写状态或外网。

另一个真正 Python SDK 示例 `templates/scene-notes`：先审代码，然后：

```bash
python scripts/plugins.py package templates/scene-notes plugin-packages/scene-notes-1.0.0.zip
python scripts/plugins.py install plugin-packages/scene-notes-1.0.0.zip --sha256 <实际ZIP的SHA256> --trust-backend
```

Python 插件是受信任服务器代码，不是沙箱。非只读 UI 需要 `--grant-capabilities`；后台需要 `--trust-backend`。来源／整个包哈希变化会失去授权；拒绝覆盖内置、现有安装、路径穿越、symlink 和超限包。远程安装须 HTTPS＋可信 SHA256；没有浏览器点击任意 GitHub 自动执行的功能。

SDK：[docs/PLUGIN_SDK.md](docs/PLUGIN_SDK.md) · 发布：[docs/GITHUB_PUBLISH.md](docs/GITHUB_PUBLISH.md)

## 双模型与 TTS 配置

仅填服务器 `.env`／部署环境，勿提交 Git：

- `GEMINI_API_KEY`、`GEMINI_MODEL`：知识模型与可选地图布局。
- `DECISION_API_KEY`、`DECISION_BASE_URL`、`DECISION_MODEL`：OpenAI 兼容决策模型。未确认 jev 身份，接口保持可配置。
- `TTS_API_KEY`、`TTS_BASE_URL`、`TTS_MODEL`、`TTS_VOICE`：兼容 `/audio/speech` 的 TTS。模型／voice 由供应商实际支持情况决定，勿把配置存在当作已验收。
- `ENABLE_DEMO`：无外部模型演示。真实模式正式账号房主在主持设置开启；游客不能使用付费模型／服务端 TTS。
- `PLUGIN_COMMUNITY_URL`：你实际发布的 GitHub 仓库 HTTPS URL；未填就明确显示未发布，不虚构线上市场。
- `DATA_DIR` 等完整参数见 `.env.example`。WebSocket 使用同源验证；前后端分开开发时使用 Vite 代理，不绕过 Origin 检查。

浏览器朗读使用你设备的 Web Speech 声线，不保存文件，也不保证每个浏览器都有中文 voice。服务端 TTS 单音频上限 5 MiB；仅成员且模块开启、当前分支仍引用时认证读取。回档或关闭不会撤销已经发出的付费服务调用；异步冲突可能产生未引用文件。当前没有费用硬额度、持久任务队列或供应商 exactly-once 计费。

## 开发与验证

```bash
pip install -r requirements-dev.txt
npm ci --prefix web
npm run build --prefix web
python -m pytest -q
python -m compileall -q server plugins scripts templates
python -m playwright install --with-deps chromium
# 另开终端启动服务器，然后：
python tests/browser_smoke.py
python tests/browser_plugins.py
```

当前插件 ZIP 无 Node 构建依赖；UI 单入口 ui.js 内联到独立 frame，CSS 可自行注入。Python 支持插件包内相对 helper 导入；所有文件参与信任哈希。改内置插件后必须审阅并执行 `python scripts/plugins.py lock-builtins`。**不要在 CI 自动更新此锁来掩盖未审阅变更。**

测试包括原内核回归、新插件权限／开关／幂等／分支／迁移／隔离／异步冲突、两个真实 Chromium 浏览器的拖动／回档。浏览器朗读测试使用 speechSynthesis stub；TTS 使用 MockTransport，所以不等于真实音频听感或供应商成功。

详细结果：[docs/TEST_REPORT.md](docs/TEST_REPORT.md)。GitHub CI／Release 工作流已随仓库提供；实际检查状态请看仓库 Actions，不把本地测试替代线上执行结果。

## 数据、备份与恢复

```text
data/
  tavern.sqlite3             账号、房间、事件、快照、模块开关
  assets/<room>/<plugin>/    不可变素材文件；当前 _assets 元数据控制访问
  plugins/<plugin>/          已安装社区包
  plugin-trust.json          显式审阅过的包哈希
```

完整备份：

```bash
python scripts/backup.py --bundle --output backups/tavern-v2.zip
# 只备数据库也保留，但不能据此声称完整保存音频／插件：
python scripts/backup.py --output backups/tavern.sqlite3
```

SQLite 通过 online backup API 包含已提交 WAL，bundle 同时收集素材、插件和信任记录，并附 SHA256 manifest。备份期间不要升级／移除插件或 GC 素材；不可变文件先写后入库，可能附带未引用文件但不遗漏已引用文件。备份不包含 `.env`，含房间数据／账号哈希／可执行插件，按敏感数据保管；哈希不是加密。

恢复只到新／空目录，不覆盖现有数据：

```bash
# 先停服务；--stopped 是操作员确认，不是自动停进程。
python scripts/restore.py backups/tavern-v2.zip --target data-restored --sha256 <备份输出的SHA256> --stopped
# 检查 integrity、重新审查插件与 trust 记录，再替换数据目录并启动。
```

只恢复可信来源备份。记录服务器 key／配置并通过独立安全渠道保管；源码 ZIP 故意不带真实 DB、用户音频、已安装私人插件和密钥。

## Docker / HTTPS

```bash
cp .env.example .env
docker compose up --build -d
```

Dockerfile 带六模块、frame SDK、文档、模板和示例包，使用非 root 用户；`tavern-data` 持久化整个 `/data`，不仅是 SQLite。镜像构建本轮未实际执行。`deploy/` 的 Caddy 示例供你配置真实域名／TLS；无已部署公网生产服务。

## GitHub 生态

实际代码结构、SDK、只读 UI／Python 模板、registry、CI、插件 Release 工作流、PR／Issue 模板和审核规范已经提供。项目发布仓库为 [Tera-Dark/Ember-Tavern](https://github.com/Tera-Dark/Ember-Tavern)。提供的是插件开发与发布入口，不代表已经拥有活跃插件市场；没有虚构社区用户或插件下载量。

发布前选择许可证：`LICENSE.example` 只是 MIT 模板，不是已授予的项目许可证；仓库拥有者填写后再发布。步骤见 GITHUB_PUBLISH，贡献与安全见 CONTRIBUTING／SECURITY。

## 项目结构

```text
server/                 最小宿主、规则、API、模型服务、plugin_runtime SDK
plugins/                六个独立清单／Backend／UI；catalog.lock.json
web/                    React 宿主、模块中心、通用 iframe 桥接
static/                 已构建发行前端（直接运行用）
templates/              session-insights、scene-notes
plugin-packages/         示例发行 ZIP、实际 SHA256
registry/               示例插件索引；Release 下载 URL 由实际发布更新
launcher/               Go + WebView2 桌面启动器、任务与事务更新
scripts/                run、plugins、backup、restore
.github/                CI、Release、Issue／PR 模板
tests/                  自动测试、双浏览器内核与插件验收
docs/                   PRD／Word、SDK、发布指南、测试报告、V1存档
```

这是供小团体使用和社区继续开发的实际模块化 MVP；不冒充全规则 VTT、已上线社区或已验收的真实供应商服务。
