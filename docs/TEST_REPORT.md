# 2.2.0-beta.1 · 创作与小团体生态基础验证

2026-09-30。针对实际 FastAPI／SQLite／WebSocket／React／sandbox iframe，不是静态页面原型。旧 2.0 验证记录不代表本轮平台／供应商验收。

## 1. 环境与命令

- Linux、Python **3.11.2**、Node **22.22.3**；安装 requirements-lock，再安装测试依赖。
- FastAPI 0.142.1、Pydantic 2.13.4、Starlette 1.7.0、httpx 0.28.1、uvicorn 0.54.0。
- pytest 9.1.1、Playwright 1.63.0、jsonschema 4.26.0；本地 Chromium **153.0.8010.0**。
- 单 worker 演示服务；两个独立浏览器 context；所有供应商测试用 mock／演示，没有调用付费模型或真实 TTS。
- 浏览器只额外使用 --no-sandbox，**未关闭 web security／同源／站点隔离**；本沙箱另安装 CJK 字体用于视觉检查。

```bash
python -m pip install -r requirements-lock.txt
python -m pip install -r requirements-dev.txt
python scripts/creator.py schemas --check
python -m pytest -q
npm ci --prefix web
npm run build --prefix web
python -m compileall -q server plugins scripts templates
```

本轮最后 pytest：**107 passed，18.32s，1 条 TestClient 弃用警告**。警告来自 Starlette 对 httpx 的测试客户端提示，未掩盖；需在将来测试栈升级中关注，不等于运行失败。

## 2. 后端：保留原 51 项，加 56 项基础回归

| 范围 | 实际覆盖 |
| --- | --- |
| 原内核／插件 | 认证、操控权、幂等、行动／检定、属性后果、历史与完整回档、供应商失败；模块依赖、移动、namespace、素材引用、迁移、包信任、备份恢复 fixture |
| 统一契约 | 三种原生模板与 Draft 2020-12 Schema／运行时一致；共享插件 Schema／工具／发现；未知版本、额外／权限字段、坏颜色／URL、重复 ID、hp 越界拒绝 |
| 请求与内容边界 | API 2 MiB 声明长度／分块前置限制；原生 512 KiB／深度／节点限制；world 384 KiB；合并和补全 ID 后重新验证；直接角色／世界 extensions 深度校验 |
| 内容事务 | 预览不改 revision；合并同 ID／保留世界设置；替换与回档；角色新 ID／未分配；旧 revision 拒绝；相同 request_key 不重复导入；导出再导入 |
| 隐私 | 玩家 REST／WS／历史／搜索／插件普通上下文无 GM lore、gm_notes、provenance、证据选择；read:gm 明确 grant＋房主校验；private namespace 投影失败关闭 |
| 上下文 | 规则／常驻／精确字面关键词／词法／priority；禁用与封存未来排除；整体／lore 预算、裁剪、角色结构化属性与行动／骰子保留；演示不直接显示秘密 |
| 主持权威 | 任意 GM provider 的 Decision 和有界 GMTrace 校验；非法 prompt/debug trace 不应用部分决定，保持等待房主恢复 |
| 成员运营 | 轮换／暂停、旧码拒绝、移除／退出清 assignment／WS 4403、登出 4401、运营状态不回档；并发加入不超过 12 人 |
| 扩展基础 | 保留 core 资源／能力、SDK 骰子来源与服务端随机数、读取核心的异步冲突；传递依赖健康；未来 minimum_host 阻止可信 backend 执行 |
| 工具与目录 | 六类脚手架、拒绝覆盖／非法 ID／未知类型／symlink；不执行 backend；非对象／深递归 JSON 干净报错；ZIP 重复／drive 路径拒绝、逐跳拒绝非 HTTPS 重定向；目录与实际模板／SHA／文档一致 |
| 代理会话 | X-Ember-Session 与 Bearer 验证同会话，显式应用头优先；网关兼容路径下登出仍撤销 WS，不把 token 放进 URL |

跨字段与字节限制以运行时／CLI 为准，不能单凭 JSON Schema 检查声称所有语义合法。

## 3. 三套真实双浏览器验收

先在**独立测试 DATA_DIR**安装已审阅的 session-insights 和 dice-tray，后者 grant-capabilities，无社区 Python：

```bash
python scripts/plugins.py package templates/session-insights artifacts/session-insights.zip
python scripts/plugins.py install artifacts/session-insights.zip --sha256 <实际SHA256>
python scripts/plugins.py package templates/dice-tray artifacts/dice-tray.zip
python scripts/plugins.py install artifacts/dice-tray.zip --sha256 <实际SHA256> --grant-capabilities
python -m playwright install --with-deps chromium
# 另开终端启动同一测试 DATA_DIR 的演示服务，再执行：
python tests/browser_smoke.py --screenshots artifacts/browser-core
python tests/browser_plugins.py --screenshots artifacts/browser-plugins
python tests/browser_foundation.py --screenshots artifacts/browser-foundation
```

可用 EMBER_CHROMIUM_PATH 指定已安装的 Chromium。默认 base-url 是 http://127.0.0.1:8000，可用 --base-url 指向同一测试服务，不要对有真实用户数据／付费模式的实例运行。

### 内核

- UI 正式注册、建房／加入、分配角色、玩家行动／服务器检定、双端同步。
- 修改世界／属性／背包／压力后完整回档；成员／分配关系不回档；封存未来不进有效检索。
- 真下载完整事件档案，不含测试密码；390×844 手机操作／队伍／明暗，无横向溢出。
- 最后一轮 action 同步 **312ms**；是三套测试并行时的本地单样本，不是互联网 SLA。
- page_errors = []。

### 插件

- 真实拖动预览、松手提交、角色权限；预览未持久化；地图／台本回档、级联关闭与数据保留。
- session-insights 动态发现与导航；iframe 不能读 parent.document，context 无登录 token。
- 浏览器语音桥使用 speechSynthesis stub；未配真实 TTS 时按钮禁用，不伪装音频验收。
- 手机地图／TTS frame 没横溢；最后拖动预览同步 **128ms**（最终插件单独重跑的本地样本）。
- page_errors / console_errors = [] / []。

### 创作基础

- 上传原生世界书 → 模式／警告预览不写 → 确认替换 → 双端世界更新；玩家网络响应中无主持秘密。
- 主持上下文无费用预览显示规则／秘密的激活原因；角色导入／分配／编辑／导出，gm_notes 不发玩家、extensions 不被编辑清空。
- 主题只改本机，不改 revision／同伴配色；令牌传入隔离骰盘 UI，ctx 无秘密／token；2d6+1 结果与服务端骰子事件一致、角色属性不变。
- 390×844 实际导航／导入预览无横向溢出；创作指南在 App 中可读。
- 邀请暂停／重置、旧码／暂停加入与成员移除，玩家即时转为无法入座，角色解除分配。
- **浏览器路由模拟网关移除 Authorization**，全部 UI 用应用会话头仍可玩；不是宣称已验证所有真实网关／TLS 部署。
- page_errors / console_errors = [] / []。

脱敏结果汇总：`BROWSER_RESULTS.json`。本地截图在 ignored artifacts/，查看了桌面工坊、上下文预览、主题骰盘与手机界面；不把私人房间／邀请码／token 放进发行资料。

## 4. 构建、Schema、锁与 CI

- Vite build：**1582 modules**，JS **357.53kB**（gzip 108.89kB），CSS **80.56kB**（gzip 15.27kB）；发行 static 已同步。
- `creator.py schemas --check` 无漂移；compileall 成功；内置六模块代码没变，review lock 不自动重写。
- CI 已加入 Python 3.11／3.13、Schema 漂移、前端产物一致性与三套浏览器，使用 demo／无模型密钥。工作流 YAML 能解析，但**本轮未推送／运行 GitHub Actions**，线上结果以真实 Actions 为准。
- 备份／迁移原 fixture 回归通过；本轮没有新的完整真实音频备份演练。历史 Word PRD／启动器报告标记为旧版，不冒充 2.2 实机验收。

## 5. 未验证与已知边界

1. 真实 Gemini／兼容决策／TTS 的联网、支持模型、余额、听感和音频解码；模拟 HTTP／语音 stub 不能证明供应商成功。
2. Windows 启动器完整安装、macOS、Docker 构建、真实两台 LAN 设备／远程 TLS、真实访问网关端到端复测。
3. 公网压测、完整渗透、费用／存储硬额度、注册验证、商业 SLA、多 worker／多机器一致性、持久任务、供应商 exactly-once、素材 GC。
4. 完整 D&D／CoC／路径／视线／先攻、图片美术主题与 PNG 聊天人格卡；本轮主题只为配色，ST 导入为明确子集。
5. 模型绝不剧透、第三方 Python 任意代码沙箱、完整多来源版权账本／签名市场；不作这些保证。

当前交付是你和几位朋友能继续实测的小宿主＋版本化创作／扩展基础。下一步见 ROADMAP，先实际跑一场再选需要加深的规则与模块。
