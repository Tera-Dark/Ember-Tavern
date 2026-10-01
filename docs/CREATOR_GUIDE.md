# 创作指南：把一个世界交给下一张桌

适用宿主 2.2.0-beta.1 · 内容格式 v1 · Plugin API 1

这里有两条创作路径：**内容作者写 JSON**，**模块作者写插件**。不用为了创作世界书去安装 Python 后端；不用为了加骰盘去改宿主 App。

## 1. 不写代码：从创作工坊开始

房间导航 → **创作工坊**：下载世界书、角色卡、主题的标准模板／Schema，编辑 JSON，再「校验并导入」。也可在世界书／角色档案页使用导入／导出按钮。

- 房主可导入世界书和角色卡；所有成员可在本机应用主题。
- 先看预览：条目数、规则、主持专属、停用、合并／替换影响和兼容提示；确认后才写事件与快照。
- 默认合并：同 ID 更新条目，保留房间名称／前提／基调／规则；替换覆盖整本世界书，但不清空角色与已发生剧情。另起故事应新建房间。
- 替换或有兼容／许可提示时必须勾选确认。房间变化导致旧预览失效时重新检查，不要盲目覆盖。
- 导入角色生成新运行时 ID，**不会继承操控权**；房主另外分配。
- 导出的世界书／角色卡包含主持秘密，只提供给房主。对外发布前手动清理秘密和个人信息。

模板与 Schema 也可直接取：`GET /api/creators`、`/api/creators/templates/{worldbook|character|theme}`、`/api/contracts/{worldbook|character|theme|plugin}`。指南接口只读公开文档；不需要联网模型。

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

`kind=rule` 不能把 D&D／CoC 判定、JavaScript 表达式或新的属性算法“导入成可执行规则”。目前仅支持 `ember-light/v1`：d20 + 属性 ≥ 难度，天然 1／20，失败按标注风险扣生命或加压力。新系统需要规则 adapter／迁移／测试；不知道怎么做就先用文字约定和房主补述，不伪装完整规则支持。

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

- `rule_system` 固定当前 ember-light/v1。
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

保留宿主资源：core.world/v1、core.characters/v1、core.rules/v1、core.events/v1、core.dice/v1。插件通过声明 uses 和对应 capability 使用，不能 provides core.*；未知核心资源拒绝／不可用，不能靠名称猜测内部状态。

## 7. 扩展字段与版本

世界／角色可有 `extensions: {"your-name.feature/v1": {...}}`。每个作品最多 16 个命名空间、合计 32 KiB、12 层／20,000 节点；只能存有限标准 JSON，不能改权限、运行代码或注入 AI 原始转储。扩展数据默认公开，请不要放秘密；需要权限投影的数据应做可信插件并实现 public_data。

Schema 在 `registry/`，由契约生成：

```bash
python scripts/creator.py schemas --check  # CI 检查漂移，不自动接受变化
python scripts/creator.py schemas          # 审阅契约改动后更新四个 Schema
```

JSON Schema 能帮编辑器检查结构，但 hp ≤ max_hp、唯一条目 ID、总字节、版本可用性等以官方运行时／CLI 为准。破坏性内容／资源结构应发布新 `/vN`，不是偷偷在 `/v1` 下换格式。

## 8. 发布前的清单

- 校验、导入一个空测试房、导出再校验；检查合并／替换、主持秘密和手机排版。
- 填写原作者、来源、许可；确认修改／分享／再分发权，主题图片素材或规则原文也不例外。
- 房间导出是新草稿：不会自动推断多来源的作者／许可。最近 20 次导入 provenance 仅供房主核对，不是完整署名账本；保留原文件与许可，发布时自行整理，不能把空作者／许可当成无版权。
- 不带 `.env`、登录 token、用户 DB／备份、私人素材。公开档案去掉 gm_notes／gm 条目；谨慎检查扩展。
- 插件提供 README、版本、需要的最低宿主、capabilities、依赖、回档行为、外部服务及费用；默认不开启。
- 发布 ZIP + **对应实际 ZIP** 的 SHA256，只有真实上传后才填写下载 URL。哈希不证明作者身份或安全。
- 项目 `LICENSE.example` 不是已授予许可证；正式生态发布前仍需仓库拥有者选定正式 LICENSE。

继续阅读：[架构](ARCHITECTURE.md) · [贡献规则](../CONTRIBUTING.md) · [安全](../SECURITY.md) · [LAN 使用](LAN_DEPLOYMENT.md) · [路线图](ROADMAP.md)。
