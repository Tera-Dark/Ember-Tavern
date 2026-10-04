# 维护者发布指南

目标仓库：https://github.com/Tera-Dark/Ember-Tavern。仓库已经存在，不需要再次 git init 或改写 origin。**更新于 2026-10-03：**当前源码元数据是宿主 / 网页 `2.4.0-beta.1`、桌面 / 部署引擎 `0.2.0-beta.3`；M2 / M3 均是当前开发源码，未随新 Release 发行。最新公开桌面 Release 仍为 `desktop-v0.2.0-beta.1` / 宿主 `2.3.0-beta.1`。Release dispatch 返回 403，Windows artifact 下载返回 EOF，因此没有新 EXE / SHA / smoke provenance 或 Release；详见 [M2 交付记录](M2_DELIVERY.md) 和 [M3 交付记录](M3_DELIVERY.md)。

Arena 已连接 GitHub 时直接使用 git／gh，不提供密码、PAT、OAuth token 或验证码到聊天／源码／远程 URL。连接失败请在 Arena 重新连接。自己电脑首次使用 gh，可在本机走 `gh auth login` 的官方流程，不分享凭据。

## 1. 合并前

1. 仓库拥有者决定私有／公开与许可证；LICENSE.example 仅为可选择模板，没有正式 LICENSE 前不宣称已经授予开源使用权。内容包还要分别核对 metadata.authors／license，多来源导出仅是署名待复核草稿。特别是 `presets/echo-well-srd521` 与 `presets/ashen-canal-coop` 当前标记 `UNLICENSED`，未确认再分发权前不得把它们打入公开内容发行。
2. 审阅当前分支 diff，确认 .env、data、backups、creations、cache、浏览器运行 artifacts 和私人邀请／token 不在 Git／发行包；不硬编码供应商密钥。
3. 以当前 [M2](M2_DELIVERY.md) / [M3](M3_DELIVERY.md) 交付记录和 CI 工作流为准运行 Schema、pytest、前端构建及发布所需检查；[TEST_REPORT.md](TEST_REPORT.md) 是 2026-09-30 的旧快照，不是当前验收规范。M3 当前已验证 schema、179 项后端测试、前端构建和 Python 编译，具体命令及边界见 M3 记录。付费 key 必须为空、使用隔离 DATA_DIR，不对真实团本实例跑 QA。
4. 对隐私／规则／迁移变更审阅数据兼容性；对新资源审阅公开投影／能力／版本／冲突；回档不应恢复旧邀请和已退出成员。
5. 将工作推送到**当前工作分支**并提 PR，检查真实 Actions／review。Arena 会话有固定工作分支，不在会话里换分支或直推 main；保留未覆盖验证边界。

```bash
git status --short
git diff --check
gh pr checks <PR编号>
```

## 2. 宿主发行

由拥有者在合并与实际 CI 成功后选择 tag／发布权限。宿主版本应一致于 server/version.py、web/package.json／lock、launcher-manifest.json 与文档；发布前重新构建 static，不伪造启动器的 Windows 实机测试结果。

GitHub Release 上传干净源码／static／模板／Schema／文档和锁定依赖；**不要**附运行 SQLite、.env、用户语音与完整私人备份。Docker／启动器实机还需分别验证。对版本升级说明备份与回退方案；M1 / M2 / M3 状态与主持私有资料不要直接由不认识其 schema 的旧宿主打开；当前核心 `schema_version=4`。版本回退需恢复升级前的完整备份，不能直接把新版数据库交给旧宿主。即便未来发行，未获授权的 `UNLICENSED` 样板也不可作为官方再分发内容。

历史启动器 URL 指向既有发行，不代表它包含当前 M2 源码；在新包实际构建、安装冒烟、SHA / 来源验证和不可变 Release 成功前，不更新正式下载入口，也不称源码已对公众可下载。

## 3. 插件发行

作者可各自建仓库／Release，不强迫源码合并到宿主。先审阅源码、README、metadata／许可、minimum_host、依赖、capabilities、actions、signals、hooks、provides／uses 和迁移／回档测试。Python 有完整服务器权限，绝不是 sandbox；UI 只读公共能力之外（含 read:gm）也要明确批准。

```bash
python scripts/creator.py validate templates/dice-tray
python scripts/plugins.py package templates/dice-tray artifacts/dice-tray.zip
# 工具输出 SHA256；这只是本地打包，不是上传／发布。
```

旧 session-insights／scene-notes 有对应 plugin-<id>-v<版本> 标签工作流；实际流程见 .github/workflows/plugin-release.yml，必须获得拥有者授权再打 tag／运行，不对未配置的插件承诺自动发行。

发布后验证 Release 资产确实可下载，记录实际 download_url 和 ZIP SHA256（不是运行时 package_hash），再更新 registry/index.json。既有包 SHA 本地核对不能证明旧远程 URL 可用；新 dice-tray 目前 source-only，URL／SHA 为 null，不能写一个不存在的链接。整个包变动会撤销已批准哈希，升级需备份／停服／重新审阅，不让安装器静默覆盖。

## 4. 世界书、角色与主题发行

只发布已校验的 JSON／说明／你有权分享的素材。使用标准格式 ember.worldbook/v1、ember.character/v1、ember.theme/v1；清理主持秘密／gm_notes；填写真实署名／许可与兼容说明。

目前 registry 是可检查的本地目录，不是签名市场、收入结算、恶意包自动审核或浏览器一键执行入口。提交提案时说明来源、哈希、Schema 版本与许可证；`PLUGIN_COMMUNITY_URL`仅配置你真实维护的社区入口，不表示宿主自动信任内容。

安全披露与联系渠道见 SECURITY.md；Settings → Security 的私下漏洞报告由拥有者启用。
