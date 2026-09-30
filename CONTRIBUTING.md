# 社区贡献

欢迎独立插件优先的贡献：新增能力通常放进 plugins／自己的仓库，而不是往宿主 App 堆功能。项目仓库：https://github.com/Tera-Dark/Ember-Tavern。当前为测试版，正式开源前由拥有者确定许可证；第三方 Python 仍需人工审阅。

1. 阅读 `docs/PLUGIN_SDK.md` 与 `SECURITY.md`，从 `templates/session-insights` 起步。
2. 提案说明资源契约、依赖、能力、付费行为与回档策略。默认不开启社区模块。
3. 清单、代码与说明打包；不含 .env、运行数据、任意安装时脚本或预置凭据。
4. UI 不依赖 CDN、不访问父 DOM、不处理登录 token；用户文本使用 textContent／安全转义。
5. Python 是受审查服务器代码：不要直接写 core DB，使用 Result；校验 payload 与角色；网络有超时和体积限制；on_event 不阻塞外部服务。
6. 更新 version／state_version；实现必要 migrate，使用旧 namespace 测试；资源破坏性变更发布新 /vN。
7. 运行 pytest、生产 build、受影响 browser test，注明没有真实供应商验收的部分。
8. 审阅后才能更新内置 hash lock；**CI 不自动运行任意 GitHub 下载的 Python 插件**，不使用 pull_request_target 执行外部贡献代码，不注入模型密钥。

目前安装器拒绝覆盖已有版本。维护者发布 ZIP + SHA256；校验完整性不替代代码审计。贡献 PR 不自动上架，第三方 backend 不自动获得信任。GitHub Actions 的实际执行结果以仓库 Actions 为准，本地验证不等于线上通过。
