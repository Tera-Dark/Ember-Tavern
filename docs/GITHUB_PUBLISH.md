# 发布到你自己的 GitHub

项目发布目标仓库：https://github.com/Tera-Dark/Ember-Tavern。后续发布需要拥有者授权；PAT 不要写进源码、远程 URL 或日志，使用后撤销。

## 发布前检查
1. 决定私有／公开与许可证；`LICENSE.example` 只是 MIT 模板，修改年份和持有人并命名 LICENSE 或改选其他许可证。未选择时不宣称已开源授权。
2. 确认 .env、data、backups、浏览器 artifacts 不入 Git；检查插件代码是否有硬编码 key。
3. 运行 README 的 tests/build/browser 检查。首次启用 Actions 后检查日志；以仓库 Actions 中实际完成的运行结果为准。
4. Settings → Security 启用私下漏洞报告，替换 SECURITY.md 联系渠道。

## 用 GitHub CLI（由仓库拥有者执行）
```bash
gh auth login
# 若还没有 Git 仓库：
git init
git add .
git commit -m "Release modular host and Plugin SDK v1"
# 下面的 owner/name 由你填写；--public 也可改 --private。
gh repo create <owner>/ember-tavern --public --source=. --remote=origin --push
```

主项目发布可在 GitHub Release 上传整个源码包；不要上传运行 DB、音频用户数据或 .env。示例插件的自动 Release：
```bash
git tag plugin-session-insights-v1.0.0
git push origin plugin-session-insights-v1.0.0
```

工作流在**你已授权的这个仓库**生成 ZIP + SHA256 并发布。用户按实际资产 URL 与 SHA256 安装。发布后把 registry/index.json 的 repository、download_url 更新为真实值；配置 PLUGIN_COMMUNITY_URL 后宿主可返回实际社区入口。

第三方作者通常各自建插件仓库／Release，提交 registry 提案，不强迫合并进本体。维护者检查 manifest／能力／权限／迁移／回档测试和许可证，不自动信任 Python；未知高风险 UI 也不自动授权。
