# 创作指南：把一个世界交给下一张桌

适用当前源码宿主 2.4.0-beta.1（内容 v1、预设／剧本 v1）· Plugin API 1。源码含 M3 两条实验规则样板；M4 的本地目录浏览、离线准入校验与可复用作者工作流已实现；在线市场运营、真实社区作品发布和作者验收仍未完成。公开桌面 Release 仍为旧宿主版本，M2 / M3 自动化范围与下载边界见 [M2 交付记录](M2_DELIVERY.md) 和 [M3 交付记录](M3_DELIVERY.md)；M4 进度见 [M4 交付记录](M4_DELIVERY.md)。

**新增玩法作者路径：**[玩法预设／世界书／剧本／模块组合实战](PRESET_AUTHORING.md)。数据组合、精确来源锁、原子新建房间与作者 CLI 已支持；不自动安装代码，不宣称完整 5e／SLG。

这里有两条创作路径：**内容作者写 JSON**，**模块作者写插件**。不用为了创作世界书去安装 Python 后端；不用为了加骰盘去改宿主 App。

## 1. 不写代码：从创作工坊开始

房间导航 → **创作工坊**：下载世界书、角色卡、主题的标准模板／Schema，编辑 JSON，再「校验并导入」。也可在世界书／角色档案页使用导入／导出按钮。

- 房主可导入世界书和角色卡；所有成员可在本机应用主题。
- 先看预览：条目数、规则、主持专属、停用、合并／替换影响和兼容提示；确认后才写事件与快照。
- 默认合并：同 ID 更新条目，保留房间名称／前提／基调／规则；替换覆盖整本世界书，但不清空角色与已发生剧情。另起故事应新建房间。
- 替换或有兼容／许可提示时必须勾选确认。房间变化导致旧预览失效时重新检查，不要盲目覆盖。
- 导入角色生成新运行时 ID，**不会继承操控权**；房主另外分配。
- 导出的世界书／角色卡包含主持秘密，只提供给房主。对外发布前手动清理秘密和个人信息。

模板与 Schema 也可直接取：`GET /api/creators`、`/api/creators/registry`（本地基础目录／兼容元数据）、`/api/creators/templates/{worldbook|character|theme}`、`/api/contracts/{worldbook|character|theme|plugin|registry-index}`。目录 API 只公开版本化元数据，不实时核验远程链接、不自动下载或安装；指南接口只读公开文档，不需要联网模型。

## 2. 命令行建立作品

在项目根目录、已安装 Python 依赖的环境运行：

```bash
python scripts/creator.py init worldbook creations/my-world --id my-world --name "我的世界"
python scripts/creator.py init character creations/my-hero --id my-hero --name "我的角色"
python scripts/creator.py init theme creations/my-theme --id my-theme --name "我的配色"
python scripts/creator.py validate creations/my-world/worldbook.json
```

这只写指定的新／空目录；不覆盖已有作品、不执行插件。`--id` 使用 3–48 位小写字母／数字／连字符，字母开头。目录不存在可创建；符号链接目标不接受。`creations/` 不是自动安装目录，且默认不入 Git／镜像；发布时整理到自己的作品仓库。

所有作品有 `format` 和 `metadata`：`id`、`name`、`version`、`description`、`authors`、`license`、`tags`。作品 version 是最多 32 字符的三段数字（例如 1.0.0），与 `/v1` 格式版本不同。模板许可为空，**请自行确认授权、填写真实署名与许可**；工具不会替你授予别人的版权。

## 3. 世界书：设定、规则与秘密

标准文件：`templates/worldbook/worldbook.json`；格式 `ember.worldbook/v1`。

```json
{
  "format": "ember.worldbook/v1",
  "metadata": {
    "id": "my-world", "name": "雾中的旧港", "version": "1.0.0",
    "authors": ["填写真实署名"], "license": ""
  },
  "world": {
    "title": "雾中的旧港", "premise": "你们调查一座失踪的灯塔。",
    "tone": "探索与悬疑", "rule_system": "ember-light/v1",
    "lore": [{
      "id": "old-lighthouse", "title": "旧灯塔", "content": "渡船停在灯塔南侧。",
      "tags": "地点 港口", "keys": ["灯塔", "渡船"], "kind": "lore",
      "visibility": "public", "enabled": true, "activation": "keywords", "priority": 10
    }],
    "extensions": {}
  }
}
```

| 条目字段 | 怎么写 |
| --- | --- |
| id | 稳定、唯一，最多 64 字符；可用字母／数字／`_`／`-`；不要拿修改后的标题作版本 ID |
| title / content | 标题最多 80、正文 1–3000 字符；短条目比一本大段提示词更容易控制预算 |
| keys | 最多 24 个字面关键词，每个 60 字符；中英文均可，不执行正则 |
| tags | 普通文本标签（120 字符），兼作词法匹配辅助；不是权限声明 |
| kind | `lore` 是资料；`rule` 是桌面约定，优先进入主持上下文 |
| visibility | `public` 发给房间成员；`gm` 仅房主和主持上下文，不发给玩家 |
| enabled | false 时不参与 AI 检索／激活；公开停用条目仍可在世界书中阅读 |
| activation | `always` 常驻优先；`keywords` 先字面关键词，也有词法相关度回退，并非严格“关键词不命中就永不出现” |
| priority | −100…100；同类激活中数字大者优先，不越过规则／常驻的基础排序 |

最多 160 个条目，整本 `world` 紧凑 UTF-8 数据另限 384 KiB；文件上限 512 KiB。缺少／空 ID 的兼容条目会获得可复现 ID，但改了正文后生成 ID 也会变，正式作品请明确写稳定 ID。合并相同 ID 会替换该条目，所以多位作者尽量用作品前缀防碰撞。

`kind=rule` 只是主持上下文中的文字约定，不能把 D&D／CoC 判定、JavaScript 表达式或新的属性算法“导入成可执行规则”。当前宿主审阅的规则身份有 `ember-light/v1`、实验 `dnd5e-srd-5.2.1/v1` 与实验 `ember-coop-settlement/v1`。后两项只覆盖有限战斗／合作经济循环，明确不支持的内容见 [M3 交付记录](M3_DELIVERY.md)；不要称为完整 5e 或 SLG。预设中的规则身份也不会单独启用代码；选相应锁定玩法预设新建房间，不能只改 worldbook 字段切换规则。尚未支持的规则请由房主裁决，不要以提示词冒充机械结算。

### 检查 AI 是否看到了该看的资料

房主「主持设置 → 主持上下文预览」，输入可能的行动。会显示选中的标题、原因、裁剪与省略情况，不发模型请求、无供应商费用。默认全上下文 24,000、世界资料 6,000 序列化字符，最多 32 条资料；这是字符预算，不是 token／费用承诺。

保留真正必要的规则／常驻，避免全书都设 always。禁用和封存未来不进记忆；行动、骰子、属性不会为了塞大量世界书而被随意丢弃。

**主持秘密会被真实模型看到。**客户端数据隔离不等于模型绝不剧透。测试、检查叙事；绝不放密钥、现实隐私或不可公开的个人资料。已经公开过的内容，改成 gm 不能撤回同伴已经读到／下载的数据。

### 兼容导入不是完整兼容

支持旧余烬世界 JSON（`title` + `lore`）和 SillyTavern 风格 `entries` JSON；不是运行酒馆插件／提示词扩展的兼容层。

- 主关键词、常驻和停用可转换；兼容条目默认 **public / lore**，不会猜测哪些是秘密。
- 正则条目会停用；次级词／选择性、位置、深度、角色注入、概率等不完整移植并给提示。
- 同一条超过 3000 字符、重复 ID、未知原生版本、非法字段或超限会拒绝，不静默截断整本世界。
- 想修改转换后的 visibility／触发方式，先把原文件整理为原生模板，再校验；UI 预览不会替你编辑文件。

```bash
python scripts/creator.py validate old-book.json --kind worldbook
```

CLI 返回格式来源、摘要与 warnings；它不会把 JSON 中的代码执行，也不自动拉取 URL。

## 4. 角色卡：档案不是权限

标准文件：`templates/character/character.json`；格式 `ember.character/v1`。

- `rule_system` 标识规则身份；标准角色卡当前可标记 `ember-light/v1`、`dnd5e-srd-5.2.1/v1` 或 `ember-coop-settlement/v1`。导入角色必须与房间当前规则匹配，不能通过角色卡切换规则；5e 数值通过专用规则工作台修改，通用档案页只编辑叙事字段。
- `character` 包含 name、archetype、avatar、description、hp、max_hp、stress、attributes、inventory、gm_notes、extensions。
- 生命 0–100、最大生命 1–100、hp ≤ max_hp；压力 0–6；五项属性 strength／dexterity／knowledge／insight／charisma 为 −3…5；背包最多 24 项。
- description／背包默认共享；gm_notes 最多 2000 字符，仅房主／主持上下文。
- **不能包含 id、assigned_to、owner_id 或账号字段**；运行时 ID 和分配关系由房间创建。
- 旧普通角色 JSON 可转换；PNG 卡、Character Card v2 聊天人格／角色扮演提示词尚不支持，不冒充标准角色档案。
- 编辑既有角色保留备注与 extensions；编辑窗口抓取打开时 revision，房间更新后需重新检查，不能静默覆盖。

## 5. 主题：安全、个人化、可传递

标准文件：`templates/theme/theme.json`；格式 `ember.theme/v1`。`modes` 至少有 dark 或 light，每个模式提供全部 15 个令牌，值必须是 `#RRGGBB`：

```text
--bg --surface --surface-2 --surface-3 --border
--text --muted --faint --gold --gold-hover --gold-bg
--green --green-bg --red --red-bg
```

不接受 CSS、脚本、URL、字体下载或图片资源。主题保存于本机浏览器，不改房间、不给别人自动换肤，也不产生剧情 revision；「恢复默认主题」只移除自定义配色，保留当前深／浅模式。宿主会把配色传给隔离插件，插件作者使用 CSS 变量才能适配。

这是配色包基础，不是完整美术 UI 包；排版布局、动画、地图图像、头像素材上传后续走独立资源／插件路线。请自行检查文字对比度与手机可读性，安全校验不等于无障碍质量认证。

## 6. 模块作者：三个起步模板

```bash
python scripts/creator.py init plugin-ui creations/my-panel --id my-panel --name "我的面板"
python scripts/creator.py init plugin-backend creations/my-notes --id my-notes --name "我的附注"
python scripts/creator.py init plugin-dice creations/my-dice --id my-dice --name "我的骰盘"
python scripts/creator.py validate creations/my-dice
```

| 模板 | 路线 | 权限／注意 |
| --- | --- | --- |
| session-insights / plugin-ui | 纯 UI、公共房间／事件阅读 | 默认关闭，无 Python，不需要重新 build 宿主 |
| scene-notes / plugin-backend | Python Result 写独立 namespace | 需审阅代码与 `--trust-backend`，不是沙箱 |
| dice-tray / plugin-dice | `EmberSDK.roll()` → 服务器自由骰 | 需 `dice:roll`、uses core.dice/v1、`--grant-capabilities`；最低宿主 2.2.0 |

插件清单额外提供 authors、license、HTTPS homepage、minimum_host。minimum_host 使用数字基版，不区分 beta；具体字段、Result 生命周期、版本／冲突、跨模块能力与资源见 [Plugin SDK](PLUGIN_SDK.md)。

```bash
python scripts/plugins.py package creations/my-dice artifacts/my-dice.zip
python scripts/plugins.py install artifacts/my-dice.zip --sha256 <打包输出的实际SHA256> --grant-capabilities
```

刷新模块中心、房主启用即可看到导航。`validate`／`package` 只查结构与入口，不做代码审计、不执行后端、不授予信任。`read:gm` 也需要显式 grant；只读公共面板不要申请它。

保留宿主资源：core.world/v1、core.characters/v1、core.rules/v1、core.events/v1、core.dice/v1、core.campaign-state/v1。M2 `core.campaign-state/v1` 只返回公开 Ledger、行动方式与公开轮次，不暴露 `gm` 条目或主持摘要。插件通过声明 `uses` 和对应 capability 使用，不能 `provides core.*`；未知核心资源拒绝／不可用，不能靠名称猜测内部状态。完整版本 / 状态边界见 [M2 交付记录](M2_DELIVERY.md)。

## 7. 扩展字段与版本

世界／角色可有 `extensions: {"your-name.feature/v1": {...}}`。每个作品最多 16 个命名空间、合计 32 KiB、12 层／20,000 节点；只能存有限标准 JSON，不能改权限、运行代码或注入 AI 原始转储。扩展数据默认公开，请不要放秘密；需要权限投影的数据应做可信插件并实现 public_data。

Schema 在 `registry/`，由契约生成：

```bash
python scripts/creator.py schemas --check  # CI 检查漂移，不自动接受变化
python scripts/creator.py schemas          # 审阅契约改动后更新十个 Schema
python scripts/registry.py                # 离线校验本地目录与精确包锁
```

JSON Schema 能帮编辑器检查结构，但 hp ≤ max_hp、唯一条目 ID、总字节、版本可用性等以官方运行时／CLI 为准。破坏性内容／资源结构应发布新 `/vN`，不是偷偷在 `/v1` 下换格式。

M4 目录当前仍是仓库内基础索引，并非在线市场。`scripts/registry.py` 只读本地模板、插件 ZIP 和预设锁，不访问 URL、不解压到磁盘、不运行作品代码；其 `valid` 结果不代表许可证、作者身份、链接可用性或独立试玩已认证。社区投稿、兼容报告和维护／撤下请求入口见 [registry 说明](../registry/README.md) 与 GitHub Issue 模板。

## 8. 作者 CI 与 GitHub Release

三份可复用工作流位于 Ember-Tavern 仓库：[社区验证](../.github/workflows/community-validate.yml) 可在作者自己的仓库校验预设／剧本／世界书／角色卡／主题／模块；[预设 Release](../.github/workflows/community-preset-release.yml) 与[插件 Release](../.github/workflows/community-plugin-release.yml) 会在匹配的版本 tag 上构建归档并发布 ZIP 与对应的 SHA-256。它们只读取投稿为数据，不运行投稿中的插件代码；校验通过不等于安全审计、授权认证、在线可用性检查或真人试玩。

调用方必须把**工作流路径和 `sdk_ref` 都固定到 Ember-Tavern 中经过审阅的 40 位 commit SHA**；建议用同一个 SHA。不要使用 `@main`、分支名或可移动 tag。以下 `<...>` 是占位符，需换成一个真实、不可变的 40 位十六进制 SHA，不能原样复制运行：

```yaml
name: Validate Ember work
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  validate-preset:
    uses: Tera-Dark/Ember-Tavern/.github/workflows/community-validate.yml@<reviewed-40-hex-commit-sha>
    with:
      kind: preset
      source_path: creations/my-preset
      sdk_ref: <same-reviewed-40-hex-commit-sha>
```

发布工作流应由**已经存在且指向本次源码 commit 的版本 tag**触发；工作流会核对调用 ref、tag、清单 ID／版本一致，并拒绝源路径穿越或符号链接。作者仓库需要给 release job `contents: write` 权限；开启 tag protection，并只允许可信维护者触发发布：

```yaml
name: Release preset
on:
  push:
    tags: ['preset-my-preset-v*']
permissions:
  contents: read
jobs:
  release:
    permissions:
      contents: write
    uses: Tera-Dark/Ember-Tavern/.github/workflows/community-preset-release.yml@<reviewed-40-hex-commit-sha>
    with:
      preset_path: creations/my-preset
      release_tag: ${{ github.ref_name }}
      sdk_ref: <same-reviewed-40-hex-commit-sha>
```

插件版本 tag 使用 `plugin-<id>-v<version>`，改调用 `community-plugin-release.yml` 并传 `plugin_path`。工作流要求明确作者／许可，插件清单或预设及其组件锁通过 CLI 校验；发布出的 `.zip.sha256` 是对本次实际归档字节计算的，不是签名。要让发行资产保持不可变，版本号变更时创建新 tag／Release，不覆写旧资产。

**Release 不会自动改 Ember-Tavern 的中央目录。** 发布后作者仍须按 [玩法作品投稿](../.github/ISSUE_TEMPLATE/preset-submission.yml)、[插件提案](../.github/ISSUE_TEMPLATE/plugin.yml) 以及 [目录维护／状态更正](../.github/ISSUE_TEMPLATE/registry-maintenance.yml) 的流程提交目录更新 PR。维护者会复核来源、许可、兼容锁、下载资产与所需证据；`python scripts/registry.py` 不联网下载远程资产。中央索引变更通过 CI 后也不表示获得真人试玩或官方推荐等级。

## 9. 发布前的清单

- 校验、导入一个空测试房、导出再校验；检查合并／替换、主持秘密和手机排版。
- 填写原作者、来源、许可；确认修改／分享／再分发权，主题图片素材或规则原文也不例外。
- 房间导出是新草稿：不会自动推断多来源的作者／许可。最近 20 次导入 provenance 仅供房主核对，不是完整署名账本；保留原文件与许可，发布时自行整理，不能把空作者／许可当成无版权。
- 不带 `.env`、登录 token、用户 DB／备份、私人素材。公开档案去掉 gm_notes／gm 条目；谨慎检查扩展。
- 插件提供 README、版本、需要的最低宿主、capabilities、依赖、回档行为、外部服务及费用；默认不开启。
- 发布 ZIP + **对应实际 ZIP** 的 SHA256，只有真实上传后才填写下载 URL。哈希不证明作者身份或安全。
- 项目 `LICENSE.example` 不是已授予许可证；正式生态发布前仍需仓库拥有者选定正式 LICENSE。

继续阅读：[架构](ARCHITECTURE.md) · [贡献规则](../CONTRIBUTING.md) · [安全](../SECURITY.md) · [LAN 使用](LAN_DEPLOYMENT.md) · [路线图](ROADMAP.md)。
