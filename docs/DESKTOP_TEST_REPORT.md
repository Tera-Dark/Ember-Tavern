# 房主桌面 0.2.0-beta.1 验收

日期：2026-10-01。宿主 2.3.0-beta.1，部署引擎 0.2.0-beta.1。

## 本地与浏览器

- 后端：114 项通过（含 7 项身份密钥 / 权限 / 撤销回归）。
- Electron / Vue / TypeScript / Vite 构建成功；7 项桌面测试通过：IPC 主 frame、ID / URL / 操作允许列表、唯一 EXE 文件名、跨实例并发凭据写入、加密失败不落盘、Vue proxy 到 IPC JSON 的序列化。
- Go 测试 / race / vet 通过；内容 schema 无漂移，Python compileall 通过。
- 隔离开发预览使用真实 Go 部署引擎、Python venv、宿主与 Chromium，而非模拟返回值：主题切换、安装启动、房主自动登录建房、移动端浏览器身份 + 密钥入座、插件开关、停服、API 保存后不回显均通过，page errors 为 0。

## Windows 原生构建

工作流：[Desktop build and Windows package](https://github.com/Tera-Dark/Ember-Tavern/actions/workflows/desktop.yml)。发行以对应 Release 的 `desktop-smoke.json` 与成功 Actions 记录为准，不用旧失败 run 代替最终结果。

发行前 [Windows run 36816933981](https://github.com/Tera-Dark/Ember-Tavern/actions/runs/36816933981) 全部通过（代码 `796fa5a`）。原生 CI 真正构建两个 EXE、用 NSIS 静默安装，然后启动**安装目录中的真实 Electron 程序**：验证 sandbox / context isolation / no Node、切换主题、随包本体安装启动、房主建房、无注册访客认证、嵌入冒险桌登录、关闭冒险窗口后控制台仍可操作、房间插件开关、停止、API key 保存 / 不回显、应用优雅退出。

跨平台缺陷已作为修复提交保留：LF 内容包信任散列、UTF-8 文本读取、POSIX 备份清单路径、Python 3.13 深层 JSON 验证、销毁后不可访问 game.webContents，以及 Vue reactive proxy 不可原样跨 Electron IPC。没有通过重写信任锁 / 关闭沙箱来掩盖失败。

## 未验收与边界

- Windows CI 的宿主环境使用 runner 的 Python / 依赖；没有宣称验证了全新用户设备的首次官方下载 / 全离线安装。
- 未进行代码签名。未验证用户实际网卡 / VPN / 防火墙 / SmartScreen 行为、完整卸载重装、跨 Windows 用户的数据迁移。
- 没有真实付费模型 / TTS 请求、音频听感或供应商预算验证；API 设置中使用假测试值。
- 普通 LAN HTTP 不加密；Python 社区插件属于完整信任代码，不是沙箱。
- 桌面与宿主是 beta，保留单 worker / 每房 12 人的基础边界。

操作指南：[DESKTOP_GUIDE.md](DESKTOP_GUIDE.md)。
