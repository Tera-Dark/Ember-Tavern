# 历史快照：启动器 0.1.0-beta.2 · 验证报告

> **报告日期：2026-09-30。**本文仅是当时原启动器／2.1 本体的验证记录；其中 2.2 / 2.1 版本信息和测试结果均非当前状态。当前源码元数据为宿主 2.4.0-beta.1、桌面 / 部署引擎 0.2.0-beta.3；公开桌面 Release 仍为 0.2.0-beta.1，M2 尚无已验证安装器。详见 [M2 交付记录](M2_DELIVERY.md)。

2026-09-30。酒馆本体更新为 2.1.0-beta.2；版本展示统一使用版本号与测试版，不用场景化发布命名。

## 已完成

- Go 单元 / 安全 / 真实进程集成 **18 项通过**，包含 `-race` 检查；`go vet` 通过。
- 真实 Chromium 操作：创建 → 安装独立 venv → 预检 → 启动 → 日志；page errors=[]，手机无横向溢出。
- 真实酒馆数据验证：创建账号、房间、生成地图后「更新并重启」，账号仍可登录，原房间、地图 namespace、角色位置保留，服务 PID 改变。
- 故障注入集成：新代码预检通过但真实启动失败；恢复旧代码 / 环境 / 原 DB，失败迁移写入不进入原数据，旧服务自动重启。
- ZIP 路径越界 / 大小 / 重复项、下载 SHA 不匹配不执行、端口冲突、并发任务、单目录锁、索引损坏、更新 journal 恢复。
- 配置密钥不返回 UI、不进日志；只允许固定配置键；接口 URL 不可含凭据，远程需 HTTPS。
- 生产管理 API 的 cookie、Host / Origin、修改请求头拒绝测试。
- 本体原 **51 项 pytest 全通过**；没有为启动器删改核心业务能力。
- Windows x64 EXE 交叉构建成功，PE Machine=0x8664，GUI subsystem=2，带余烬图标 / 版本 / DPI manifest，约 8 MB。
- 官方 Python 3.13.15 x64 完整 ZIP HTTPS 下载及 SHA256 已验证；含 pip / venv，便携解压，不运行系统安装器、不修改注册表或 PATH。

## 验证限制

- UI / 安装 / 更新实测使用 Linux 与明确开发 Python 覆盖；不是 Windows 安装环境。
- Windows 自动下载安装、WebView2 宿主、SmartScreen、杀毒拦截、权限与局域网防火墙需用户实机验收。
- 没有签名证书，不伪装成已签名或微软认证的安装包。
- GitHub CI / Release 的实际状态以仓库 Actions、Release 与提交为准；不把交叉构建或本地测试当作线上与 Windows 桌面验收。
- 当前只支持 Windows x64 原生窗口；macOS / Linux 是开发浏览器模式，不是正式桌面安装包。
- 更新器会保留备份 / 回退环境，尚未做磁盘配额与自动清理；大量素材更新可能占用额外磁盘。

## 源码与接口

`launcher/` 是独立启动器；`ui/` 为自包含 Web UI，`internal/engine/` 管实例、下载、环境、任务、进程和事务回退。不会把地图 / TTS 业务搬进桌面程序；桌面只部署酒馆服务并打开浏览器。

## Beta.2 Windows 兼容收尾

GitHub Windows runner 已执行官方便携 Python 下载 / SHA / 解压 / venv + ensurepip 导入并通过。首次 Windows CI 发现英文区域 CP1252 下中文 stdout 编码问题，以及测试自身未关闭索引锁；Beta.2 强制子进程 UTF-8，并修测试关闭。Windows 完整进程集成与桌面 GUI 的最终结论分别以新 Actions / 实机验收为准。
