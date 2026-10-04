# 余烬酒馆 Plugin SDK v1

**M1 / M2 新只读资源：**`core.campaign/v1` 返回当前剧本公开进度；M2 新增 `core.campaign-state/v1`（能力 `read:room`），返回公开任务／NPC／资源、行动模式与轮次，不包含 GM Ledger 项、主持记忆摘要或来源。示例 `templates/campaign-compass`；M2 Schema / API 与公开下载边界见 [M2_DELIVERY.md](M2_DELIVERY.md)。

当前源码元数据：宿主 / 网页 2.4.0-beta.1 · Plugin API 1 · 文档更新 2026-10-03。M4 目录索引／离线校验仍在建设；公开 Release 仍是旧版，不能用源码元数据推断已发行。详见 [M4 进度记录](M4_DELIVERY.md)。

[创作指南](CREATOR_GUIDE.md)（世界书／角色／主题／脚手架） · [整体架构](ARCHITECTURE.md) · [LAN 部署](LAN_DEPLOYMENT.md)

目标：让第三方开发者新增模块时不修改 `server/app.py`、`web/src/App.jsx` 或前端打包入口。房主按房间开启；默认关闭社区插件。地图、图标、台本、声音都不是账号／房间／事件内核的一部分。

## 1. 五分钟：安装独立 UI 示例

在项目根目录执行：

```bash
python scripts/plugins.py package templates/session-insights plugin-packages/session-insights-1.0.0.zip
# 命令输出这个实际 ZIP 的 SHA256；复制该值，或使用随发行包的 .sha256 文件。
python scripts/plugins.py install plugin-packages/session-insights-1.0.0.zip --sha256 <实际SHA256>
```

刷新房间「模块中心」，开启「会话观察板」。导航自动出现，角色生命、轮次、有效事件与时间线实时更新。**不需要重新打包前端或重启 UI 插件服务。**示例不调用网络、不写状态、不需要 Python 后端信任。

## 2. 包结构和清单

```text
my-plugin/
  plugin.json
  ui.js           # 可选；原生 JavaScript，无 CDN；需自行 bundle 为单个 UI 入口
  backend.py      # 可选；受信任的 Python 后端（类名 Extension）
  README.md
```

最小清单参见 `templates/session-insights/plugin.json`。也可用 `python scripts/creator.py init plugin-ui my-plugin --id my-plugin` 创建，或选择 plugin-backend／plugin-dice。`creator.py validate` 不执行 Python；`registry/plugin.schema.json` 与发现／安装／打包共用 `server/contracts/plugin.py`，未知额外字段拒绝。字段：

| 字段 | 约束／含义 |
| --- | --- |
| id | 小写字母起始；小写字母、数字和连字符，3–48 字符；安装目录同名 |
| name / description / version | 用户可读名称、描述、发行版本；version 由作者维护 |
| authors / license / homepage | 可选真实署名／许可／HTTPS 项目链接；缺省不代表获得授权 |
| minimum_host | 三段数字，默认 2.1.0；比较宿主数字基版（忽略 beta 后缀），高于当前版本不加载；roll／core 资源／个人主题／新隐私 API 的模块请声明至少 2.2.0 |
| api_version | 目前只支持整数 1；其他主版本不加载 |
| state_version | 状态 schema 版本，须与 Python `Extension.schema_version` 一致 |
| backend / frontend | `backend.py`／`ui.js`，不需要时为 null；不支持任意文件路径 |
| default_enabled | 社区插件应设 false；内置 AI 主持默认 true |
| ui.group / label | 自动导航分组与标题；同组主面板提供导航标题 |
| ui.slot / height | `toolbar` 或 `main`；iframe 高度（像素） |
| requires | 必须启用的插件 ID；启用自动补齐，关闭级联关闭依赖者 |
| uses / provides | 读取／提供的版本化资源契约，例如 `scene.map/v1` |
| hooks | 当前可声明 `gm` 主持提供者；同时只允许一个 |
| actions / signals | 允许的持久化操作名／瞬态信号名 |
| capabilities | 只读权限、本地语音、跨插件调用、模型与素材能力；不是客户端可伪造的免审通行证 |

同一个房间中，同一资源契约只能有一个启用提供者。先关闭旧提供者再开启替代品。依赖目前以插件 ID 为单位；**尚不实现 npm 式版本范围、自动升级或通用服务发现依赖求解器**。

## 3. UI SDK

宿主提供 `window.EmberSDK` 和 `#plugin-root`。UI 运行在独立文档、`sandbox="allow-scripts"` iframe 中；不能使用父页 React、DOM、sessionStorage 或 `fetch` 访问网络。

```javascript
EmberSDK.onContext(ctx => {
  const root = document.getElementById('plugin-root');
  root.textContent = `${ctx.room.title}：第 ${ctx.room.turn} 轮`;
});
```

`ctx` 包含：`api_version`、`plugin_id`、`plugin_revision`、`branch`、`user`、`is_owner`、`own_state`、安全裁剪的 `room`、最近有效 `events`、声明的 `resources`、模块开启状态 `integrations`、主题变量和浏览器 voice 名称。**没有会话令牌、供应商密钥、服务器环境变量或完整房间配置。**`read:room` 即使由房主打开也只给公共世界／角色；`gm` 条目、gm_notes、provenance 与私有上下文选择不会发给普通 UI。`read:gm` 需显式部署者 grant，且仅房主获得额外秘密；核心 UI 资源仍公共。不要把私人凭据写进世界书。

| 方法 | 用法 |
| --- | --- |
| onContext(fn) / getContext() | 订阅最新房间／插件上下文；返回取消订阅函数 |
| invoke(action, payload, target?) | 调用本插件或获授权目标；Promise 只返回 Result.output |
| signal(name, payload, target?) | 发瞬态信号，不写事件；无持久化成功回执 |
| onSignal(fn) | 接收来自声明 uses 资源提供者的信号 |
| notify(text, kind) | 宿主提示；kind 为 success 或 error |
| roll(expression) | 需 dice:roll 和 uses core.dice/v1；服务器权威自由骰，返回 rolls／modifier／total／request_key，记录 source_plugin；不是 pending_check 检定 |
| speak(text, {rate,voice}) / stopSpeech() | 需 `local:speech`；最多 3000 字符；浏览器／系统朗读，不保存文件 |
| asset(assetId) / downloadAsset(assetId) | 需 `asset:read`；认证读取／下载本插件音频或图像，返回 data_uri／下载回执 |
| audio(assetId) | 需 `asset:audio`；读取本插件当前时间线音频，返回 `{data_uri}` |
| downloadAudio(assetId) | 需 `asset:audio`；宿主认证下载本插件音频 |

15 个主题颜色令牌由宿主发送到 ctx.theme，bridge 自动同步为 frame 的 CSS 变量；UI 使用这些变量，不依赖父 DOM。个人主题不改变 room revision 或朋友的配色。完整令牌见创作指南。

跨插件授权既可以绑定 ID：`invoke:map-tokens.move`，也可以绑定资源：`invoke-resource:scene.tokens/v1.move`。资源能力必须同时在 `uses` 声明对应契约；父页解析实际 owner，服务端再次校验目标的 `provides`。信号对应 `signal:`／`signal-resource:`。

```javascript
const tokenResource = EmberSDK.getContext().resources['scene.tokens/v1'];
await EmberSDK.invoke('move', {
  character_id: '角色ID', map_id: '当前地图ID', x: 5, y: 8
}, tokenResource.owner);
```

SDK 文本插入 DOM 请使用 `textContent`，或完整 HTML 转义；不要直接把角色名、模型输出放进 `innerHTML`。

## 4. Python 后端 SDK

Python 插件不是沙箱。部署者必须读过代码、审过依赖和能力，再使用 `--trust-backend`。

```python
from server.plugin_runtime.sdk import Plugin, Result

class Extension(Plugin):
    schema_version = 1

    def initial(self, ctx):
        return {'notes': []}

    async def action(self, ctx, name, payload, data):
        ctx.require_owner()  # 或针对玩家仅控制自己角色的权限校验
        if name != 'append':
            raise ValueError('Unknown action')
        text = payload.get('text')
        if not isinstance(text, str) or not 1 <= len(text) <= 500:
            from fastapi import HTTPException
            raise HTTPException(422, 'text 必须是1–500字符')
        data = ctx.own_data()
        data['notes'] = (data.get('notes', []) + [text])[-20:]
        return Result(data=data, message='附注已更新。', output={'saved': True})
```

### Context

- `ctx.room_id`、`ctx.room`、`ctx.state`、`ctx.user`：本次调用快照；事件钩子的 user 为 None。不要从此快照直接写数据库。
- `ctx.own_data()`：取得自己 namespace 的深复制。
- `ctx.resource(name)`：只能读取 manifest.uses 声明的资源；返回 `{owner, revision, data}` 或 None。
- `ctx.require_owner()`：服务端校验房主，不信任 iframe 传来的角色。
- `ctx.control(character_id)`：返回允许控制的角色；房主可控全部、玩家仅 assigned_to 为自己，否则抛 403。
- `ctx.save_asset(bytes, mime)`：需 `asset:write`；写入当前 room/plugin 的不可变素材文件；单文件最多 5 MiB。允许 MP3、WAV、PNG、JPEG、WebP。返回 id/mime/bytes；必须把返回元数据加入 Result.data 的 `_assets` 列表，提交成功后才能被认证读取。

### Result 与生命周期

- `Result(data=...)` 仅替换当前插件 data。宿主写 namespace revision、保存事件和完整游戏快照；插件不直接修改 core state。
- `Result.calls=[{'plugin':ID,'action':操作名,'payload':{...}}]` 是受 capability 约束的跨插件调用；最多 16 次调度、最多 8 个写 namespace，超限／循环拒绝；本次各 namespace 最后一起提交。
- `Result.output` 返回给 UI；勿包含密钥、大文件或原始音频。
- `initial(ctx)`：首次开启时建立状态；关闭／再开不重新初始化。
- `migrate(data, old_version)`：由插件自行实现升级；默认遇到不匹配 schema 拒绝。升级前备份并使用已有状态测试。
- `resources(ctx,data)`：返回 `{资源名:资源数据}`；只注册 manifest.provides 声明的契约。
- `on_event(ctx,event,data)`：同步小型钩子，不做付费网络调用；返回新 data 或 None。异常隔离并记 `_plugin_faults`，不阻止内核事件。
- `signal(ctx,name,payload)`：服务端校验瞬态数据／角色，返回待广播 payload；默认拒绝。
- `public_data(ctx,data)`：默认返回共享数据。私密 namespace 必须按 ctx.is_owner 投影，并测试 REST／历史／UI 资源；投影异常返回空，不能回退原始数据。可信 Python 能读取原始服务器资料，不是能力沙箱。
- `gm(ctx,state,mode)`：仅给声明 hooks:["gm"]、model:gm 的提供者；所有提供者返回的 Decision 和 `server/contracts/hosting.py` GMTrace 都由宿主校验后再应用。trace 只允许有界 mode／label／retrieval_count／duration_ms／knowledge／decision／context_ids／context_selection；记忆摘要诊断只给房主来源 ID、字符数、截断状态，不给玩家或普通插件。禁止任意 prompt/debug dump。空 label 用清单名称。mode 应诚实对应房间 demo／live，演示不可暗中收费。规则执行仍在内核；文本规则不能改判定。

### 状态与并发

`state._plugins[ID] = {schema_version, revision, data}`；单 namespace 序列化上限 256 KiB。前端无需自行带 token 或版本，父页 invoke 自动加入：

```json
{"expected_plugin_revision":3,"expected_branch":1,"request_key":"唯一请求键","via":"来源插件","payload":{}}
```

服务端按 room/plugin 串行、按 request_key 幂等；已提交同一请求直接返回当前房间。异步结束前核验本插件、读取依赖和 branch；读取 core 资源还把房间 revision 记入冲突检查；冲突 409 时 UI 应重新获取上下文，不能静默覆盖。不同 namespace 操作不依赖全部剧情 revision，地图可以在 GM 生成期间移动；最终 GM 状态合并保留新的插件 namespace。

**外部服务不是数据库事务**：调用可能已经收费，但回档、关闭、冲突或崩溃会令结果无法提交，留下未引用文件；不得宣称付费调用能撤销或 exactly-once。当前没有生产级供应商幂等、后台队列或费用硬额度。

### HTTP API

- `GET /api/plugins`：安装目录、SDK 文档和可用性，需登录。
- `POST /api/rooms/{room}/extensions/{plugin}/toggle`：房主；enabled、expected_revision、request_key；依赖图与资源冲突校验。
- `GET .../extensions/{plugin}/context`：房间成员＋插件开启，返回安全 UI context。
- `POST .../extensions/{plugin}/actions/{action}`：成员＋插件能力＋action 内角色校验。
- `GET /api/rooms/{room}/assets/{plugin}/{asset}`：成员＋开启插件＋当前有效 namespace 引用；其他时间线或关闭模块不可取。
- `GET /plugin-frame/{plugin}?bridge=...`：公开代码壳，**没有房间数据**；bridge 只是随机消息通道，不是登录 token。
- WS `plugin_signal`：带 branch、plugin_id、via、name、payload；目前每用户每房间最多 30 条/秒、单信号约 8 KiB。

## 5. 资源契约

`GET /api/rules` 是公开只读的宿主规则目录；当前列出 `ember-light/v1` 与两条标为实验的 M3 子集（`dnd5e-srd-5.2.1/v1`、`ember-coop-settlement/v1`）。目录只列出经审阅的宿主代码适配器，不提供插件安装／注册接口；插件的 `Result` 不能修改规则状态。各规则的版本、范围和未支持项见 [M3 交付记录](M3_DELIVERY.md)，不表示完整 5e / SLG。

| 名称 | 提供者 | 主要数据 |
| --- | --- | --- |
| core.world/v1 | @core | 公共世界设定；需 read:room |
| core.campaign-state/v1 | @core | 公开战役 Ledger、行动模式与轮次；GM 内容和主持摘要不包含；需 read:room |
| core.characters/v1 | @core | 公共角色＋当前分配；需 read:room |
| core.rules/v1 | @core | 权威规则 ID／描述／dice 限制／Decision schema；需 read:room |
| core.events/v1 | @core | 最近 30 条当前分支事件，隐藏秘密证据；需 read:events |
| core.dice/v1 | @core | 规则 ID／自由骰限制；需 dice:roll |
| scene.map/v1 | scene-map | id/title/width/height/grid/source/seed；grid 字符 `. # ~ t =` |
| scene.tokens/v1 | map-tokens | map_id；tokens[] 含 id/name/avatar/assigned_to/position |
| map.generator/v1 | map-generator | AI 布局是否配置；不含 key |
| narration.script/v1 | narrator-script | lines[]：id/speaker/text/kind/source_event_id |
| narration.audio/v1 | voice-tts | clips[]：id/line_id/voice/bytes；tts 配置状态（非联网验收） |

`core.*` 命名空间保留；插件不能提供／替换，使用还需对应清单权限，未知契约不读取内部数据。宿主资源表在 contracts/resources.py，creator catalog 可查询。其他资源仍由可信提供者负责公开投影和字段语义；uses 不是通用私有资源 ACL。共享 resources 只应输出公共数据，不要将 owner-only namespace 自动映射成可被所有插件读取的资源；细粒度资源等级见后续路线图。破坏性变更用 /vN。

地图生成是程序网格／模型结构化布局，不是图像生成。可走格只有 `.` 和 `=`。地图插件移动检查整数格、边界、障碍、角色控制权；不做路径可达性、视线或距离消耗。M3 有独立的有限 5e 先攻样板，但它未接入地图坐标，也不是完整战棋。

## 6. 安装、审核与发布

```bash
# 本地只读 UI
python scripts/plugins.py install bundle.zip --sha256 <SHA256>
# 下载：必须是 HTTPS，必须给可信来源的 SHA256
python scripts/plugins.py install https://github.com/<owner>/<repo>/releases/download/<tag>/bundle.zip --sha256 <SHA256>
# Python 后端：明确审核信任
python scripts/plugins.py install backend-bundle.zip --sha256 <SHA256> --trust-backend
# 无 Python 但声明写入／语音／跨模块等非只读能力的 UI（read:gm 也需审核）：单独授权
python scripts/plugins.py install ui-bundle.zip --sha256 <SHA256> --grant-capabilities
```

拒绝路径穿越、符号链接、超限包、覆盖内置插件、覆盖现有安装。信任记录绑定**整个包的文件哈希**；文件变化自动失去授权。哈希是完整性检查，不是数字签名或安全审计。

直接放入 `data/plugins/<id>` 也能发现，但后台／高风险 UI 未授权时被阻止。UI 热安装无需宿主构建；后端执行环境、依赖更新和彻底卸载建议停服，避免进行中的调用。升级当前采用「备份 → 关模块 → 停服 → 移出旧目录并重新审核安装 → 迁移测试 → 启动」，尚无浏览器一键更新器。

`.github/workflows/plugin-release.yml` 给 tag `plugin-session-insights-v*` 打包示例 ZIP 和 SHA256 并发布 Release；项目仓库为 https://github.com/Tera-Dark/Ember-Tavern；后续 tag 推送由仓库拥有者授权完成。`registry/index.json` 目前是本地基础目录，不是自动安装商店；公开 metadata 可从 `GET /api/creators/registry` 读取，作者按模板更新后运行 `python scripts/registry.py` 与 `python scripts/creator.py schemas --check`。下载 URL 只在实际 Release 发布后填写；本地 validator 不联网核验远程可用性／下载哈希，不执行插件代码，也不把审核证据自动变成官方背书。
