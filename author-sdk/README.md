# 余烬作者 SDK

这是独立的内容作者工具包，提供模板、契约、Schema、预设锁与打包、插件清单校验及发布前检查。它不启动游戏、不包含桌面和网页运行资源、不自动安装插件，也不调用 AI。版本与宿主版本分别记录在 `sdk-manifest.json`。

## 第一次使用

先从可信来源独立核对 ZIP 的 `.sha256`，再解压。Windows PowerShell 可用 `Get-FileHash -LiteralPath <ZIP路径> -Algorithm SHA256`。散列不是代码签名或版权授权。

在解压后的 SDK 根目录建立独立 Python 3.11+ 环境：

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python ember-creator.py --help
python ember-creator.py schemas --check
```

依赖安装会联网，模板校验 / 打包不会。下面的作品路径位于 SDK 目录之外；请按自己的工作目录调整。

```bash
python ember-creator.py init worldbook ../my-world --id my-world --name "我的世界"
python ember-creator.py validate ../my-world/worldbook.json
python ember-creator.py init preset ../my-game --id my-game --name "我的冒险"
# 编辑组件、填写实际署名与再分发许可后：
python ember-creator.py lock-preset ../my-game
python ember-creator.py release-check ../my-game --tag preset-my-game-v1.0.0
python ember-creator.py package-preset ../my-game ../release/my-game-1.0.0.zip
```

插件示例：

```bash
python ember-creator.py init plugin-ui ../my-panel --id my-panel --name "我的面板"
python ember-creator.py validate ../my-panel
# 填写 plugin.json 的作者与许可，审阅代码后：
python ember-creator.py release-check ../my-panel --tag plugin-my-panel-v1.0.0
python ember-plugins.py package ../my-panel ../release/my-panel-1.0.0.zip
```

`release-check` 只检查许可声明、契约、组件散列和标签，不证明作者身份、版权、第三方代码安全或实际可玩性。模板默认清空作者 / 许可，必须由作者填写；预设所有组件也要填写，不能只改最外层清单。

## 投稿与目录审核

```bash
python ember-community.py prepare ../my-panel ../release/my-panel-1.0.0.zip ../submission --repository https://github.com/<owner>/<repo> --source-commit <40位作品提交> --sdk-commit <40位SDK提交> --tag plugin-my-panel-v1.0.0
python ember-community.py verify-release ../submission ../verification.json
```

作品公开发行应附 `release-provenance.json`；可用相同参数调用 `provenance` 单独生成该文件，或由锁定 SDK 的社区 Release workflow 生成。`prepare` 只输出本地材料；`verify-release` 会匿名访问公开 GitHub，其他命令不联网。

维护者通过 `review`、`stage` 输出目录 PR 补丁，通过 `maintenance` 输出版本维护草稿。维护者命令需用 `--index` / `--root` 指向完整目录仓库；独立 SDK 不包含完整目录和历史发行包。工具不自动上架、不运行作品代码。详见 `docs/COMMUNITY_REVIEW.md`。

## 兼容与来源

SDK 使用随包固定的契约和内置模块散列，升级 SDK 不自动改旧作品或已创建的游戏房间。改作品组件后显式重新生成锁，再提高作品版本；`--refresh-plugins` 会按当前 SDK / 本机模块刷新 pin，不能把它当作静默升级步骤。生成包后到匹配宿主实际导入和验证。

Python 后端仍是受信任服务器代码；打包不执行它，不授予任何安装或能力信任。主题 / 世界 / 角色 / 剧本数据不能注册规则代码。

详见 `docs/AUTHOR_SDK.md`、`docs/CREATOR_GUIDE.md`、`docs/PRESET_AUTHORING.md`、`docs/PLUGIN_SDK.md` 与 `templates/README.md`。包内部分文档链接指向完整宿主仓库；此 SDK 不提供游戏服务器的运行资源。

如果清单标记 `source_dirty: true` 或 `publication_ready: false`，这是本地开发包。当前仓库许可尚待确认，工具包生成不代表允许公开再分发。
