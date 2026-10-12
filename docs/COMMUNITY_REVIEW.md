# 目录投稿、发行核验与维护

本轮提供作者材料生成和维护者本地审核工具，不自动提交 Issue / PR、发布 Release、安装模块或修改当前目录。原有 `scripts/registry.py` 继续完全离线；联网仅发生在维护者显式执行 `verify-release` 时，且只访问公开 GitHub 发行和资产域名，不读取私有 API 配置或发送部署者凭据。

## 作者：准备可审阅材料

先完成作品署名 / 许可和内容锁，使用 Creator 的 release-check 与对应打包工具。预设及每个组件必须有明确作者 / 许可；官方 UNLICENSED 样板不会被工具当成可公开发行作品。

```bash
python scripts/creator.py release-check my-plugin --tag plugin-my-plugin-v1.0.0
python scripts/plugins.py package my-plugin release/plugin.zip
python scripts/community.py prepare my-plugin release/plugin.zip artifacts/my-submission --repository https://github.com/<owner>/<repo> --source-commit <40位作品提交> --sdk-commit <40位SDK提交> --tag plugin-my-plugin-v1.0.0
```

独立 SDK `0.2.0` 中用 `ember-community.py`，其余参数相同。源码与实际 ZIP 的文件内容必须一致，不能拿新清单配旧归档。作者输出包含 `submission.json`、锁定 ZIP、`release-provenance.json` 和可粘贴到投稿 Issue 的 `SUBMISSION.md`。材料不包含本机绝对路径；源码 URL 固定到公开仓库的精确 commit。

`submission.json` 只能申请 `community-submitted`。它声明模板 / 预设暂存路径、版本、散列、规则 / 插件依赖、作者 / 许可和内容提醒；不能自行标记试玩通过或官方推荐。生成不认证权属或独立作者身份。

实际公开发行的 `community-preset-release.yml` / `community-plugin-release.yml` 会生成相同格式的 `release-provenance.json` 并随 ZIP / SHA256 发布。来源声明绑定作品 commit、审阅过的 SDK commit、发行 tag 和实际包字节。手动发行可使用 `community.py provenance`，但声明仍是发布者提供的可审阅材料，不是签名或独立复现构建证明。

## 维护者：核验发行，记录审核，生成 PR 草稿

```bash
python scripts/community.py verify-release artifacts/my-submission artifacts/verification.json
python scripts/community.py review artifacts/my-submission artifacts/verification.json artifacts/review.json --reviewer "维护者名称" --reason "实际审阅范围与已知限制"
python scripts/community.py stage artifacts/my-submission artifacts/verification.json artifacts/review.json artifacts/catalog-patch
```

核验公开 GitHub Release、tag 对应 commit、SDK 提交、唯一资产身份 / 文件名 / 大小、ZIP SHA256、包内内容锁和发布者的来源声明；逐个重定向仅允许 GitHub HTTPS 资产域名，限制下载 / 解压大小，不提取或执行远程 Python / JavaScript。报告只核验发行记录与字节，不代表作品可玩、代码安全或作者授权真实。

`review` 是维护者明确作出的本地审核记录，包含审阅者、理由、时间、投稿 / 核验报告 / 原索引的散列；文件本身不是数字签名或维护者账号认证。准入审核要依赖维护者自己取得并保管的独立核验报告，不接受作者的“已核验”文字代替检查。版权与源码审查由实际维护者完成。

被拒绝或待修改的材料可在没有成功联网核验时记录：

```bash
python scripts/community.py review artifacts/my-submission - artifacts/rejection.json --decision needs-changes --reviewer "维护者名称" --reason "发行资产缺失，需要作者补齐"
```

`stage` 再核对投稿、审核和当前索引散列；过期审核拒绝继续。它在临时副本上把新作品加入完整目录并运行离线 validator，通过后输出**补丁目录**：候选 `registry/index.json`、新增的版本源码 / 本地插件包，以及审核、核验、原投稿和来源声明记录。保留原输入便于公开资产消失后仍可追溯。已有目录身份 / 版本不能覆盖；旧版本保持原锁。当前目录、数据库、房间和信任记录均不改动。维护者审阅补丁后再通过正常 PR 合入；工具不会自动写 GitHub。

## 归档 / 不兼容 / 待维护

先独立核对当前 index 文件的实际 SHA256，再执行：

```bash
python scripts/community.py maintenance artifacts/maintenance-patch --kind plugin --id my-plugin --version 1.0.0 --expected-index-sha256 <原索引SHA256> --decision archive --reviewer "维护者名称" --reason "实际归档原因"
```

状态可选择 `archive`、`incompatible` 或 `maintenance-needed`。只产生目录改动草稿与维护记录。归档 / 不兼容时移除公开下载入口，但保留版本身份、本地包和 package hash；预设归档散列会随移除下载入口一并留空，之前的发行身份仍可从来源 / 审核记录追溯。任何操作都不删除旧作品目录、旧房间或插件安装数据。

## 契约与限制

新增 `ember.community-release/v1`、`ember.registry-submission/v1`、`ember.registry-review/v1`，与 Creator / API 共享 Schema。生成 Schema 总数为十三份；作品目录仍保持 `registry_version: 1`，没有将官方样板伪装成社区作品。

失败报告不记作“已是最新”或“已通过”。当前匿名 GitHub 配额、公开资产缺失和正式许可仍可能阻止真实发行核验。旧发行没有 provenance 时需要维护者取得相应来源材料；工具不会凭空补造证据。实际作者、第三方模块、真实贡献与公开版本升级验收仍是 M4 未关闭项。
