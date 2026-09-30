# 快速启动与部署指南

这是 **2.1.0-beta.1 测试版**。通用轻规则，不是完整 D&D / CoC 或战棋系统。无模型密钥也能体验演示主持、多人房间、地图、移动、台本和回档。

## 一键启动（Windows x64）

双击 `ember-launcher-0.1.0-beta.1-windows-x64.exe`，新建实例，点「创建并启动」。首次自动下载运行环境和依赖；看到「运行中」再进入。实例菜单可检查更新与更新并重启。详见 `launcher/README.md`。

完整 Windows 安装实机验收尚待执行；下面保留手动启动方式用于开发 / 故障排查。

## 1. 下载

在仓库页面点 **Code → Download ZIP**，或下载 Releases 中的测试版包。解压后进入包含 `server/`、`static/`、`requirements-lock.txt` 的目录。

只运行不需要 Node / npm；`static/` 已构建。需要 Python 3.13 和联网安装 Python 依赖。

## 2. 启动（选自己的系统）

### Windows PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 65536
```

不需要修改 PowerShell 执行策略。若已存在自己的 `.env`，不要再覆盖；密钥只填服务器 `.env`，不要贴聊天或提交 Git。

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
cp .env.example .env
.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 65536
```

本次自动与浏览器测试在 Linux / Python 3.13 执行；Windows / macOS 命令提供为操作指南，并未宣称已在两平台实测。

打开 `http://localhost:8000`，试玩无需任何模型 key。关服务按终端 Ctrl+C，数据在 `data/`，再次启动继续保留。

## 3. 真正一起玩：只启动一个共享服务

**每个人各自启动一份服务，不是同一个房间，邀请码不能跨服务器。**

- 同一局域网：一人启动；其他人用浏览器访问这台电脑的局域网 IP，如 `http://192.168.1.20:8000`。IP 以你自己的电脑为准。
- 仅在可信局域网做无付费密钥试玩；可能需要允许系统防火墙的私有网络访问，不要关闭整个防火墙。
- 不同网络：用可信 VPN / 组网，或部署 HTTPS 服务器。不要为了测试就把未限额付费接口和普通 HTTP 登录直接开放公网。
- 用临时测试账号和独立密码，不要复用重要密码。

## 4. 三个人也能轻松开始

1. 大家分别注册正式测试账号；房主创建房间、复制邀请码。
2. 同伴加入；房主在「角色档案」分配操控者。
3. 「模块中心」开「地图生成器」和「角色图标与移动」；场景地图作为依赖自动开启。
4. 到「场景地图」选程序生成，种子填 42。程序网格无需 key，不是 AI 美术图。
5. 各自拖自己的图标；同伴看到实时预览，松手才落格与记事件。
6. 开「TTS 旁白」，自动开启台本。浏览器朗读用设备声线，不生成 MP3；真实 TTS 必须另配服务器服务。
7. 不需要的模块可关，数据不删；事件档案回档恢复地图位置 / 台本，成员与模块开关不回档。

## 5. 实验时优先测这些

- 分配后能否只操控自己的角色；能否双端同步行动和移动。
- 关闭 / 再开地图是否保留；回档能否恢复位置和台本。
- 手机是否可读、可操作；浏览器有没有中文朗读声线。
- 遇到错误时记录浏览器、系统、复现步骤、已脱敏日志，提交 GitHub Issue。不要上传 `.env`、账号 DB、完整备份或 token。

完整功能说明见 `README.md`；开发插件见 `docs/PLUGIN_SDK.md`。
