# 内容作者与模块开发者的贡献入口

项目仓库：https://github.com/Tera-Dark/Ember-Tavern。当前为 2.2 测试基础，正式开源前由拥有者确定 LICENSE；贡献／示例不等于已授予所有素材许可。

## 先选择正确的一层

- 地点、NPC、桌面约定、秘密：世界书 JSON；人物：角色卡；配色：主题包。先读 `docs/CREATOR_GUIDE.md`，从 `scripts/creator.py init` 建作品，不为纯数据加 Python。
- 地图／台本／声音／骰盘／面板：独立 plugin，按房间开启；普通新模块不应向 App.jsx 或 server/app.py 加硬编码导航。
- 新可执行规则：先提选定系统与契约／迁移方案，进入 rules adapter；不能仅导入文字就声称全规则兼容。
- 横跨权限、数据投影与兼容性的改动，先读 `docs/ARCHITECTURE.md` 和 SECURITY，不用前端隐藏代替授权。

## 内容贡献

1. 填稳定 ID、格式、发行版本、真实署名、来源与许可；检查再分发权。
2. 官方 CLI 校验；空测试房导入／导出再校验；试合并／替换、预算、主持秘密和手机 UI。
3. 角色不带运行时 ID／分配；主题只用允许令牌。extensions 默认公开，不能藏私人信息。
4. 不提交私人世界、账号 DB、备份、token、.env。公开作品先去掉 gm 条目和 gm_notes；保留原作者授权与出处。

## 模块贡献

1. 读 SDK／安全文档，从 plugin-ui／plugin-backend／plugin-dice 脚手架起步。
2. 提案声明资源 `/vN`、最低宿主、依赖、最少能力、读／写权限、付费行为、关闭／回档策略；社区默认关闭。
3. 清单与单入口 UI／可选 backend 打包；无凭据、CDN 或安装时执行脚本。UI 不访问父 DOM、网络、登录 token，用户／模型文本用 textContent／安全转义。
4. Python 是已审查服务器代码，不是沙箱；不要直接写 core DB，使用 Result，校验 payload 与角色。私密 namespace 实现 public_data，失败关闭；resources／event／output 同样不能泄密。
5. 网络调用有超时／体积边界、费用说明与异步冲突处理；on_event 同步小型操作，不阻塞付费服务。
6. 更新作品 version／state_version，必要 migrate，用旧状态和回档快照测试；破坏性资源变更新 /vN。
7. read:gm／高风险 UI 明确 grant，backend 明确信任；发布实际 ZIP + SHA。哈希不替代作者验证／审计。

## 本地检查

```bash
python -m pip install -r requirements-lock.txt
python -m pip install -r requirements-dev.txt
npm ci --prefix web
python scripts/creator.py schemas --check
python -m pytest -q
npm run build --prefix web
python -m compileall -q server plugins scripts templates
```

Schema 更新要先审契约再 `creator.py schemas`，不要手改生成文件。内置插件代码变更必须人工审阅后 `plugins.py lock-builtins`；**CI 不自动更新锁来掩盖变化**。

受影响浏览器测试另开单 worker 演示服务后运行；基础测试需安装已审阅骰盘并 grant：

```bash
python tests/browser_smoke.py
python tests/browser_plugins.py
python tests/browser_foundation.py
```

完整安装与执行见 README／TEST_REPORT。PR 说明测试命令、兼容／迁移与未验证平台／供应商；别把 MockTransport／speech stub 当付费联网／音频验收。

CI 检查 Python 3.11／3.13、Schema 漂移、生产前端、三套双浏览器流程；实际执行状态以 Actions 为准。不会在 CI 自动下载／运行第三方 Python、不使用 pull_request_target 跑外部贡献代码、不注入模型密钥。

当前安装器拒绝覆盖已有包；升级按备份／关闭／停服／重审／迁移／重启进行，不靠改文件跳过 hash。贡献 PR 不自动上架或获得信任；公开生态发布见 GITHUB_PUBLISH 和 ROADMAP。
