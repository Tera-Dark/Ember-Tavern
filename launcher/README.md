> **Windows 用户入口已升级为 [余烬桌面 Electron 房主控制台](../docs/DESKTOP_GUIDE.md)**。新版本部署引擎为 0.2.0-beta.1，保留下面的 CLI / 旧 Web 管理维护能力。不要把旧 0.1 EXE 当作新版 Electron 桌面。

# 余烬启动器 · 0.2.0-beta.1 测试版

Windows 10 / 11 x64 原生窗口（Go + WebView2），约 8 MB。参考集中式实例管理的首页、卡片和任务入口，不复制 Comfy 商标；余烬酒馆本体仍保留独立模块架构。

## 普通使用

1. 双击 `ember-launcher-0.1.0-beta.2-windows-x64.exe`。
2. 「新建实例」填名称；测试版本通道适合固定版本，main 通道获取最新源码。
3. 点「创建并启动」：下载官方 Python、准备实例依赖、拉项目、预检服务。
4. 状态显示「运行中」后点「进入实例」。首次需联网；不要求预装 Python / Git / Node，也不修改系统 Python PATH。
5. 卡片右上菜单可以改设置、查看日志、检查更新、打开数据目录。

WebView2 不可用时自动打开系统浏览器的本机管理页面；完整桌面窗口依赖微软 WebView2。第一次下载与依赖安装的网络访问、杀毒阻拦、便携运行环境行为仍需 Windows 实机验收；没有宣称 Linux 测试等同 Windows 验收。

## 更新与保留数据

- 固定仓库 `Tera-Dark/Ember-Tavern`；不是任意 GitHub 地址自动执行器。
- 使用 GitHub commit ZIP 拉取源码，无需 Git 客户端。Release 版本解析到具体 commit，main 同样固定本次 commit。
- 新代码、依赖环境先准备；备份账号 / 房间 / 素材 / 插件。
- 在数据副本上预检迁移与健康，停止服务后原地替换 `app` / 环境指针 / 数据目录。
- 失败自动恢复旧代码、环境、原数据；失败后的新数据副本保留，不默默丢弃诊断材料。
- 更新中断有 journal；下次启动恢复到旧版本再允许启动。
- 停止 / 关闭启动器只管理它自己启动的进程，不扫描、杀死其他 Python 服务。
- 更新后保留 `previous-app` / `previous-data` 与 ZIP 备份。当前没有自动备份过期清理；请定期检查磁盘。
- 更新源是信任边界，哈希不是安全审计。安装仓库代码 / pip 依赖是显式信任该项目，第三方 Python 插件仍需单独审核。

默认目录：`%LOCALAPPDATA%\EmberTavern`。

```text
launcher.json                     实例索引（单目录单启动器锁）
runtimes/python-3.13.15/           专用基础运行环境，不动系统 PATH
instances/<id>/
  app/                             原地更新的应用代码
  environments/<id>/               版本化依赖环境
  python-path                      当前环境指针
  data/                            账号、房间、地图、音频、自装插件
  settings.json                    本机配置 / 密钥（不提交、不回显）
  backups/                         更新前完整备份
  previous-app/ previous-data/      回退资料
  update-journal.json              仅更新过程中存在
```

## 多人

实例是服务器，不是玩家客户端。其他人访问同一个实例才是同一房间。打开「允许局域网访问」时，游戏服务绑定所有网卡；启动器管理接口仍只监听本机。不要直接公开未限额的付费模型或 HTTP 登录。防火墙是否允许访问由系统控制，不会自动关闭防火墙。

## 开发

```bash
cd launcher
go test ./...
# 真实 subprocess / venv / 回退测试（需要项目 Python 依赖）：
EMBER_LAUNCHER_TEST_PYTHON=python3 go test -race ./...
# Windows 构建：
go run github.com/tc-hib/go-winres@v0.3.3 make --arch amd64
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-H windowsgui -s -w" -o ember-launcher.exe .
```

Linux 开发模式可用 `--dev-python python3 --preview --listen 0.0.0.0:8765`。preview 不含生产认证，应只在受控开发环境使用，不把它当部署配置。生产只监听 127.0.0.1，并校验管理 cookie、Host、Origin 和修改请求头。

本轮构建出了有效 Windows x64 PE GUI EXE；本机浏览器实测与 Go 集成测试见 `docs/LAUNCHER_TEST_REPORT.md`。Windows SmartScreen / 签名 / WebView2 / 自动 Python 安装完整流程未做实机验收；当前 EXE 无代码签名，不建议关闭系统安全功能来忽略未知风险。
