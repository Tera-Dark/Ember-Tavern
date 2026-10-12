# 更新底座验证记录

日期：2026-10-12。桌面 / 部署引擎 `0.2.0-beta.4`，宿主 `2.4.0-beta.1`。当前为含未提交修改的本地开发构建，未创建 GitHub Release，不是干净提交的正式发行证据。

## 已执行

- `npm run build --prefix desktop`：TypeScript / Vue 检查及两套 Vite 构建通过。
- `npm test --prefix desktop`：32 项通过。覆盖语义版本 / beta 顺序、分页、历史安装包检查、回退提示持久化、新版重新提示、失败回退不抑制、重启恢复实例、安装版 / 便携资源选择、完整流式下载、坏散列 / 截断文件、重定向与来源限制、坏偏好文件保护。
- `go test ./...` 和 `go vet ./...`：通过。另设 `EMBER_LAUNCHER_TEST_PYTHON` 指向本机 Python 3.12 后，包含真实 venv / uvicorn 子进程的完整 Go 测试通过（约 408 秒）。新回归验证升级后写入较新进度、回退恢复旧进度、较新进度仍存在对应快照、服务恢复运行、提示抑制。
- `node desktop/tests/update-helper-smoke.cjs`：Windows 上实际执行 PowerShell 辅助程序，通过安装版与便携版两条分支。使用独立临时目录和合成 Go EXE，检查退出等待、中文 / 空格 / 单引号路径、安装参数、便携原文件备份和替换后启动标记；未调用用户安装器。
- `node desktop/tests/updates-ui-smoke.cjs`：本次打包的原生 Electron 窗口通过。检查回退后提示消失、选择历史版本、更高版重新提示、原生更新按钮可用，页面错误为零。GitHub 返回由测试替换，未执行真实桌面更新。
- 两条辅助 PowerShell 脚本由 Windows PowerShell Parser 解析，通过。
- Windows x64 NSIS / portable 打包成功，并生成各自 SHA256。产物在本机 `desktop/dist/update-foundation-beta4-native/`，源码来自开发树而非不可变正式发行提交。
- 版本协调检查及 `git diff --check`：通过。

## 限制与未执行

- 真实匿名 GitHub API 查询遭遇当前出口配额限制；未声称核验新的线上版本或完成公网下载安装。离线测试覆盖限流错误和短期缓存。
- 当前 Windows 工具链没有启用 cgo，`go test -race` 无法执行；普通测试、真实进程回归和 vet 已通过。
- electron-builder 默认解压临时目录的重命名遇到 `EPERM`，新的输出目录仍复现。使用同版本已经解压的 Electron 分发目录作为 `electronDist`，避开该本机重命名步骤后打包成功；没有修改依赖源码或用户现有安装。
- 未运行新的安装器替换用户当前安装，未在用户真实数据库上降级，未安排真人 / 朋友测试。合成更新辅助程序测试和原生窗口测试不等同于 GitHub 已发布版本之间的安装升级验收。
- 未发布安装包、未替换旧 Release 资产；早期无更新逻辑的旧 EXE 仍需先升级一次。

使用、回退数据语义与发布文件约定见 [更新指南](UPDATE_GUIDE.md)。
