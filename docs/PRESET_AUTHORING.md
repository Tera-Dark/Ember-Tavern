# 玩法预设与剧本作者实战（v1）

适用：当前源码宿主 **2.4.0-beta.1+**、桌面 / 引擎 **0.2.0-beta.3+**、Plugin API 1。本页讲的是**玩法组合**，不是模型采样“预设”，也不是存档。公开桌面 Release 仍为旧版，不能假设它含有此分支所有功能；源码 / 下载边界见 [M2 交付记录](M2_DELIVERY.md) 和 [M3 交付记录](M3_DELIVERY.md)。通用世界书 / 角色 / 主题与插件参考分别见 [CREATOR_GUIDE.md](CREATOR_GUIDE.md)、[PLUGIN_SDK.md](PLUGIN_SDK.md)。

## 1. 你能做什么，不会自动做什么

一套玩法 = **世界书 + 有限剧本 + 角色模板 + 叙事政策 + 已安装、已审阅模块的精确绑定**。

- 作者无需写 Python 就能做调查、轻规则探索、日常关系场景；也可选择已有 M3 实验规则预设。房主选包后一次创建新房间。
- 剧本有公开开场、GM 指引、可揭示线索、带前置条件的路线、明确结局。AI 可以叙事，不能私自改变节点、揭示状态或替玩家做选择。
- `checks=normal` 使用现有轻规则；`checks=narrative` 不让主持自动提出检定，服务器会拒绝违规提议。自由骰子仍可用。这是已有服务器政策，不是包内脚本。
- 当前宿主登记 `ember-light/v1`、实验 `dnd5e-srd-5.2.1/v1` 与实验 `ember-coop-settlement/v1`。M3 两条规则仅覆盖有限战斗与原创合作经营子集；详细支持范围 / 未支持项见 [M3 交付记录](M3_DELIVERY.md)，不代表完整 5e 或 SLG。文字规则不能改变算法，内容包与插件也不能注册核心规则。
- 数据包不含 JS / Python / HTML / `.env` / 账号 / API key / 数据库；不下载代码、不授予信任。图片 / 音频打包、本轮未支持的表达式语言、可执行脚本都不接受。
- 版本升级不自动改变旧房间；本阶段只向**新房间**应用整套组合。

## 2. 十分钟上手：改出自己的第一套组合

已经安装开发依赖或通过桌面本体提供环境时，命令如下：

```bash
python scripts/creator.py init preset creations/my-week --id my-week --name "我的小镇一周"
python scripts/creator.py validate creations/my-week
```

然后逐项修改：

1. `world/worldbook.json`：世界事实、地点、人物动机、公共 / GM 条目。
2. `story/scenario.json`：开场、线索、选择与结局。先做 3 个普通节点、2 个结局，不从 50 章开始。
3. `characters/*.json`：姓名、动机、初始属性、物品与可选规则扩展。不是玩家账号或现有角色存档；角色卡必须声明并匹配预设锁定的规则身份。
4. `preset.json`：作品 ID / 名称 / 版本、作者 / 许可、玩法和人数、引用组件、模块绑定、叙事风格。
5. `readme.md` / `licenses/content.txt`：玩法路径、测试步骤、来源与各组件许可。

修改内容文件后，其旧 SHA256 必然失效。这是防止导入时偷换组件的检查，不是故障：

```bash
python scripts/creator.py lock-preset creations/my-week
python scripts/creator.py validate creations/my-week
python scripts/creator.py package-preset creations/my-week artifacts/my-week-1.0.0.zip
```

`lock-preset` 显式更新内容 ID / 版本 / 文件散列，先校验整包再写清单。不自动更新代码模块；需要明确取本机模块时另加 `--refresh-plugins`。

网页大厅 / 创作工坊选择 ZIP → 看预览与授权提醒 → 勾选“只导入数据” → 确认；或者原生桌面使用安全文件选择器。选择导入后的精确版本，输入房间名，默认演示开桌。四位参与者时可选择房主仅主持，并分配全部角色。

**作者速度是试点目标，不是承诺。** 自动校验通过只代表契约 / 路径 / 图结构合法，不代表剧情好玩、真实模型稳定或已经得到真人反馈。

## 3. 包的文件结构和限制

```text
my-week/
  preset.json
  world/worldbook.json
  story/scenario.json
  characters/scout.json
  characters/guard.json
  characters/scholar.json
  characters/mediator.json
  readme.md
  licenses/content.txt
```

- 路径使用**小写 ASCII 相对路径**；禁止 `..`、空段、绝对路径、反斜线、隐藏段、Windows 保留名、重复路径、符号链接和特殊文件。
- 所有文件都要在清单声明；内容组件只用 JSON，附带说明用 `.md` / `.txt`。不能把整个含 README.md / 脚本 / 缓存的开发目录直接压进去。
- ZIP 最大 **1 MiB**，单文件最多 **512 KiB**，展开文本总量最多 **1.5 MiB**，最多 **48 个文件**。世界数据另限 **384 KiB**，剧本 **128 KiB**。
- 服务端在内存读取和校验，不把未信任 ZIP 解压到磁盘；拒绝加密、链接、重复项、膨胀包和非法 JSON。
- `ember.preset-bundle/v1` 是单 JSON 运输包，`files` 把相同文本保存为路径 → 文本映射。普通单独 `preset.json` 不包含所有组件，请上传打包后的 ZIP / bundle JSON。
- 不允许 NaN / Infinity、重复 JSON 字段、未知格式版本、超深 / 超多节点数据；失败不会自动降级到旧格式。

## 4. 清单字段与版本锁

`ember.preset/v1` 的主字段：

| 字段 | 用途 |
| --- | --- |
| metadata | 稳定 ID、名称、作品版本、说明、作者、许可、标签 |
| minimum_host / plugin_api | 最低宿主能力和插件协议；当前需 M1 宿主 / API 1 |
| language / play_mode | 语言；investigation / adventure / slice-of-life |
| min_players / max_players / duration_minutes | 建议人数和时长，不改变服务器 12 人硬上限 |
| difficulty / content_warnings | 新手说明、可接受内容与风险提醒 |
| rule_system / rule_version | 实际安装的规则 ID / 实现版本，不是假“全规则支持”标签 |
| profile | 叙事风格和 normal / narrative 检定政策；不包含 provider、key 或执行函数 |
| worldbook / scenario / characters / theme | 路径、元数据 ID、版本、原文件 UTF-8 字节 SHA256；主题可选 |
| plugins | 本机模块 ID、版本、完整包 SHA256、required / enabled |
| documents | 说明 / 许可文件路径和散列 |

组件引用例子（散列由 CLI 产生，不手填占位值）：

```json
{
  "path": "world/worldbook.json",
  "id": "my-world",
  "version": "1.0.0",
  "sha256": "使用 lock-preset 写入真实的 64 位散列"
}
```

完整机器参考：[preset.schema.json](../registry/preset.schema.json)、[scenario.schema.json](../registry/scenario.schema.json)。上面的解释性占位值不是合法样例，实际可校验样例在 [templates/preset](../templates/preset) 与 [presets](../presets)。

### 内容散列与运输散列不同

- 各组件 SHA256 校验**原始文件字节**，包括 BOM / 换行；修改组件后必须重新锁定。
- `package_hash` 由规范化清单和所有声明组件文本生成，标识固定组合。不同 ZIP 压缩时间 / 压缩布局不必产生不同内容版本。
- ZIP 自身 `archive_sha256` 用于运输完整性。两种散列都不证明作者身份或代码安全。
- 同一作品 ID / 版本已存在不同内容，服务器返回 409，必须提升作品版本；新版本旁存，不覆盖旧版本。

### 模块依赖与授权

```bash
python scripts/creator.py plugin-pins --id ai-host
python scripts/creator.py lock-preset creations/my-week --refresh-plugins
```

这些操作只读清单与文件散列，**不导入插件 Python**。需要的代码必须另外按插件指南安装 / 审阅 / 授权。预设不能帮作者绕过执行信任。

- 必需模块不满足精确版本 / 散列 / 原部署者信任：整套房间不创建。
- 可选模块缺失：警告并不启用；不自动联网安装。已安装且显式声明关闭的匹配模块可以留在锁中，房主之后按能力边界开启。
- 模块的 `requires` 必须一同显式锁定，不能借启用依赖偷偷带入不同版本。
- 资源提供者冲突、多个 GM 提供者不允许开桌。
- 运行中的原模块内容变化，已有房间暂不启用该模块，不静默迁移 namespace 或替换版本；关闭模块不删数据。
- 新增未锁定模块 / 不匹配版本需显式升级方案，本轮不支持对旧房间“一键改整套规则”。可以派生新作品并开新房间。

## 5. 世界书：独立事实，不是剧情脚本

1. **先写一页设定**：这个地方是什么、玩家为什么来到这里、什么值得关心。
2. **拆成自足条目**：地点 / NPC / 阵营 / 物件各一条。正文写清事实，不依赖“见上文”。
3. **给 NPC 动机与边界**：想得到什么、担心什么、什么证据会让其改变看法；不要写“无条件迎合玩家”。
4. **触发与预算**：人物 / 地点用有意义的 `keys`；少量全局约定才用 always；priority 决定预算内的选择，不保证模型遵守。
5. **主持秘密**：标 `visibility=gm`。玩家 API 和只读扩展不接收，但模型看见后仍有泄露风险；绝不能放真实私人资料 / 密钥。
6. **规则文字的界限**：kind=rule 是约定提示，不能让资源算术、伤害、权限变成作者提供的文本算法。
7. **排错**：用冒险桌“主持设置”的世界书上下文预览，看激活 / 裁剪原因，不付费调用模型。未激活时检查 keys、enabled、预算和当前位置。

导入已有酒馆世界书时先通过现有 worldbook 转换 / 校验，审阅内容与丢失字段，再保存 native v1 文件。预设包不执行 EJS / MVU / 正则脚本，也不承诺所有第三方脚本原样兼容。

## 6. 剧本：可选择、可失败、能收束

`ember.scenario/v1` 包含 objective、start_scene、scenes 和 clues：

- 场景 `text` 是公开开场；`gm_notes` 是私有指引；kind 为 scene / ending。
- 线索有稳定 ID、公开 title / text 与 gm_notes。未揭示时只在对应当前场景的 GM 面板可见。
- 推进路线有稳定 ID、公开可读标签、target 节点、`requires_clues` 与 GM 指引。前置条件可检查已揭示线索集合；M3 另外支持 `requires_rule_status`，由服务端要求某个已支持规则终态（如 `completed`、`expired`、`victory`、`defeat` 或 `retreated`）。它不是 eval / 条件脚本。
- AI 输出“已经知道某线索”不会改变 revealed_clues；玩家 facts 文本也不能绕过路线条件。
- 必须有至少一个结局，所有节点从开场可达；校验会检查线索依赖造成的明显死锁。它不代替分支试玩或证明所有复杂条件都公平。
- 每个场景至少两个解决入口 / 可接受退出是写作建议，不是机械规定；给失败的替代证据、时间 / 风险代价，避免一颗失败骰子卡死全场。
- 结局不要替玩家许诺和解或强行宣告胜利，让每个玩家回顾一个选择及其后果。

房主实际操作：玩家表达 / 行动 → 服务器检定（normal）→ 房主确认得到了证据 → 揭示线索 → 选择已声明路线 → 进入结局。等待检定 / 主持时不能推进，旧场景命令 / 过期 revision 拒绝。

### 回档与记忆

揭示集合、当前节点、结局状态、公开事实和完整来源锁进入事件快照。回档还原这些数据，封存未来不进入当前模型上下文；邀请码、成员撤销等操作权限不随剧情回档复活。模型只拿当前节点的有预算片段，不收到整个未来场景图。

## 7. 社区扩展：加一个只读剧本 HUD

样板：[templates/campaign-compass](../templates/campaign-compass)。

```bash
python scripts/creator.py init plugin-campaign creations/my-compass --id my-compass
python scripts/creator.py validate creations/my-compass
python scripts/plugins.py package creations/my-compass artifacts/my-compass.zip
```

其 manifest 仅申请 `read:room`，使用 `core.campaign/v1`。UI 通过 `EmberSDK.onContext` 读 `ctx.resources['core.campaign/v1'].data.campaign`，显示当前目标 / 场景 / 已公开线索。资源始终是公开投影，不给只读 HUD 发送 GM 指引、整个未来场景图或未揭示线索；即使房主打开 HUD 也一样。

UI 文件属于**独立插件包**，不放入预设 ZIP。安装并审阅后，在新预设里声明该模块精确版本 / 散列，重新锁定创建新房间。宿主前端不需要注册这个插件名，也不需要改核心源文件。写操作、骰子、高风险能力、资源提供者和 Python 后台另见 Plugin SDK，不能把这个只读样板伪装成规则适配器。

## 8. 测试与发布检查表

- [ ] validate 通过；每个节点、线索、引用版本有稳定 ID。
- [ ] 至少两条不同结局路线有测试步骤；普通、失败 / 退出路径都能继续。
- [ ] 玩家与只读 HUD 不收到 GM 文本；公开元数据不写主持秘密。
- [ ] 导入预览不写库；确认绑定同一 package_hash；失败不留下部分房间。
- [ ] 同请求重试只得到原房间；换配置复用 request_key 返回冲突。
- [ ] 回档到开场后没有未来线索 / 结局 / 状态。
- [ ] 缺必需依赖失败，可选依赖缺失可继续；代码信任另走审批。
- [ ] 旧房间锁固定；新版在库里旁存，不自动影响进行中的游戏。
- [ ] 作者、各组件原来源 / 许可 / 派生关系、内容提醒、可能费用明确。
- [ ] 真实 2–4 人和真实模型质量另行试点；自动化通过不冒称人气或质量认证。

本仓库官方样板当前标记 `UNLICENSED`，表示正式再分发许可待拥有者决定，不代表 CC BY / MIT 等已授权。SRD 5.2.1 署名只覆盖其中对应的 SRD 材料，不替原创故事、角色和其它资源授权。样板静态剧本也在公开源码中，**不承诺玩家无法查公开样板的谜底**。本机导入的私人作品按作者账户隔离；包散列不是读取权限。房间动态秘密仍由服务端投影保护。
