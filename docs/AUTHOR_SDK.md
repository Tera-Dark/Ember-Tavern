# 独立作者 SDK 与发布前检查

SDK 源码版本 `0.2.0`，宿主格式契约与 Plugin API 保持现有 v1。本轮提供独立、版本化 ZIP、可复现构建、清单校验和投稿 / 发行核验工具；尚未公开发行，正式许可未确定，也未成为 PyPI 包。

## 维护者构建

```bash
python scripts/author_sdk.py build artifacts/ember-author-sdk-0.2.0.zip
python scripts/author_sdk.py verify artifacts/ember-author-sdk-0.2.0.zip --sha256 <独立核对的实际散列>
```

SDK 构建 / 验证工具仅使用标准库。构建从 Git 跟踪的特定源码分类与显式 SDK 文件读取：契约 / 作者 CLI、必要服务端 Python 模块、模板、内置插件 pin、生成的 Schema、作者文档与锁定依赖。排除网页 / 桌面 / 启动器、用户数据、隐藏文件、环境文件、未跟踪的私有文件与运行产物；拒绝源目录链接和过大文件。不读取仓库外的私有 API 配置。

ZIP 固定条目顺序、时间和文件模式，同一源码 / Git 状态重复构建产生相同字节。每个文件的路径、长度和 SHA256 进入 `sdk-manifest.json`，整包输出 `.zip.sha256`。验证不解压、不联网、不导入 / 执行包内 Python；检查路径、文件数量 / 大小、重复路径 / 大小写冲突、链接、文件清单和版本根目录。未声明文件、损坏文件或散列不一致均拒绝。

`source_commit` 和 `source_dirty` 同时记录构建来源。未提交的本地改动可以构建开发包，不能冒充不可变提交的公开发行。正式模式：

```bash
python scripts/author_sdk.py build release/ember-author-sdk-0.2.0.zip --release
```

它要求干净 Git 工作区、真正的 `LICENSE` 和由仓库拥有者确认的 `AUTHOR_SDK_LICENSE.md`。后者应明确覆盖 SDK 中的代码、模板、示例与文档，并保留第三方材料所需声明。不存在这两份文件时拒绝公开模式；`LICENSE.example` 不生效。工具只检查这些声明是否存在，不提供法律或权属认证。

构建不覆盖已有 ZIP 或校验文件。新增 SDK 版本需修改 `author-sdk.json`，创建新的 `sdk-v<版本>` tag；不得覆盖既有发行。作者需要匹配宿主 / 规则 / 插件，SDK 版本不等于游戏版本。

`.github/workflows/author-sdk-release.yml` 在匹配的 SDK tag 或显式维护者 dispatch 下执行公开模式，核对 tag → commit、正式许可、整包 SHA256 和已有 Release，生成 `sdk-verification.json` 后发布新资产。普通核心 CI 只上传开发包 Artifact，不自动公开发行；本轮未运行 GitHub 发布。

## 作者独立使用

解压后的入口是 `ember-creator.py`、`ember-plugins.py` 和 `ember-community.py`；见包内 [README 源文件](../author-sdk/README.md)。Python 依赖按 SDK 自带锁文件安装，作品可以位于任意单独作者仓库，不需要游戏宿主 Git checkout、Node、Go 或 Electron。

内容作者从 init → 修改 → validate → lock-preset → release-check → package 逐步进行；插件作者从 init → validate → release-check → package 进行。打包后仍要在匹配宿主测试，不能把结构校验当作真人试玩。

## 统一发布检查

```bash
python scripts/creator.py release-check path/to/my-preset --tag preset-my-preset-v1.0.0
python scripts/creator.py release-check path/to/my-plugin --tag plugin-my-plugin-v1.0.0
python scripts/creator.py release-check path/to/worldbook.json --tag worldbook-my-world-v1.0.0
```

检查内容：原生标准格式、精确组件散列 / 引用、真实非空署名、非空且不是 UNLICENSED / UNSPECIFIED / NONE 的许可声明、清单 ID / 版本和 tag 对应。预设的世界 / 剧本 / 每张角色 / 主题逐项检查许可；兼容导入格式要先转换成原生内容。输出 `code_executed: false`，不会运行作品代码。

本地 CLI 与社区 preset / plugin Release 工作流调用同一检查，路径隔离、不可变 `sdk_ref`、tag → source commit 验证及包散列保留。目录投稿仍需独立 PR；不会自动赋予“试玩通过”或“官方推荐”等级。

## 交付边界

`ember-community.py prepare` 生成锁定投稿材料；`verify-release` 独立取回公开 GitHub 发行并核对 tag、提交和包字节。维护者使用 `review`、`stage` 生成目录 PR 补丁，使用 `maintenance` 生成精确版本的维护 / 归档草稿。详见 [投稿与维护流程](COMMUNITY_REVIEW.md)。审核不自动安装作品、授予代码信任或提升推荐等级。

此 SDK 完成的是 M4 的本地作者工具发行能力。三位非核心作者、独立作者模块、外部作者仓库真正执行 reusable workflow、已发布版本之间的旧房间验证、正式授权和真实公开资产核验仍待完成。因此 M4 保持“未完成”。
