# 余烬酒馆 v2.0 · 验证报告

日期：2026-09-30。针对实际 FastAPI / SQLite / WebSocket / React / sandbox iframe 运行，不是静态页面演示。

## 1. 自动测试

`python -m pytest -q`：**51 passed，11.98 秒，1 个弃用警告**。

- 原内核 29 项：认证、房间、角色权限、行动／骰子、服务端权威属性、重复请求、世界书、有效检索、回档、模型失败与双适配器契约等。
- 插件新增 22 项：默认与依赖／级联开关、关闭保留、程序地图与 seed=0、整数格／障碍／角色控制、跨模块及资源能力、地图／台本回档、开关不回档、幂等与旧 branch 拒绝。
- GM 延迟期间地图提交保留；事件钩子故障隔离；跨插件自循环 16 次上限；台本编辑不改正史。
- 外部 TTS MockTransport：认证 header、请求参数、素材落盘、时间线读取与回档后拒绝；合成进行中回档导致 409，未引用文件不可从素材 API 读取。
- 未受信任 Python 不执行；高风险 UI 需显式 grant，包变更撤销授权；ZIP 路径穿越／SHA 错误拒绝。
- 真正独立 UI 与已审阅 Python 模板安装／开启／操作／回档；schema 1→2 迁移；重复资源提供者冲突拒绝。
- 完整备份 fixture 验证 DB、模拟素材、Python 插件与 trust 记录恢复；拒绝覆盖已有数据；坏 manifest／损坏信任文件不破坏本体。

唯一警告来自 Starlette TestClient 对 httpx 的弃用提示；测试成功，但后续升级需关注测试客户端版本兼容。

## 2. 双浏览器内核回归

运行 `tests/browser_smoke.py`，两个独立 Chromium context、正式账号、实际 DOM 操作与 WebSocket：

| 项目 | 结果 |
| --- | --- |
| 玩家行动同步到房主 | 本次本地环境 76 ms；单次样本，不是互联网 SLA |
| 角色分配、自己行动与检定 | 通过 |
| 属性／世界修改与完整回档 | 通过 |
| 成员／角色权限不随剧情回档 | 通过 |
| 封存分支不进入有效检索 | 通过 |
| JSON 导出不含密码 | 通过 |
| 390 × 844 手机，无横向溢出 | 通过 |
| JavaScript page errors | [] |

## 3. 双浏览器插件验收

运行 `tests/browser_plugins.py`，房主实际开启地图生成、图标、TTS（含自动依赖），玩家操控分配的第二角色：

| 项目 | 结果 |
| --- | --- |
| 持续按住拖动，房主看到预览 | 本地本次 125 ms；单次样本 |
| 松手前权威位置与 DB revision | 不变，预览未持久化 |
| 松手提交 | 位置落事件，双方新格一致 |
| 玩家修改模块开关 | UI 禁止；后端房主认证另有测试 |
| 编辑台本只影响演绎 | 通过 |
| 地图／台本双端回档 | 通过；新 branch=2 |
| 关闭场景地图级联／再开 | 数据保留；开关不随剧情恢复 |
| runtime 安装 session-insights | 自动发现、开关与导航，无宿主修改／重打包 |
| iframe parent.document | SecurityError，隔离有效 |
| iframe context | 没有宿主登录 token |
| 未配置外部 TTS | 真合成按钮禁用，明确显示未配置 |
| 浏览器朗读桥 | speechSynthesis stub 接收到选定台本；不是实际听感测试 |
| 手机地图／TTS frame 横溢 | 均无 |
| JavaScript page / console errors | [] / [] |

原始脱敏摘要：`docs/BROWSER_RESULTS.json`。截图留在本次 QA 工作区；不是虚构验收图。

## 4. 构建、文档与恢复

- 生产 Vite build 成功：1576 modules；JS 328.10 kB（gzip 100.03 kB）；CSS 68.64 kB（gzip 13.37 kB）。
- compileall 成功；六个内置插件的 review hash 全部匹配。
- Word PRD：有效 OOXML，91 个段落、3 张表、2 张内嵌图（封面与模块架构），可打开并重新导出。
- YAML / JSON 语法检查通过；不是说工作流已经在真实 GitHub 执行。
- 源码 ZIP 在新目录解包、独立数据目录启动，注册／建房、6 模块发现、24×16 地图生成、2 个图标与 frame 代码壳均通过；不依赖本次 QA 运行数据。
- live DB V1→V2 启动迁移成功；online SQLite bundle 备份／新目录恢复 `integrity_check=ok`，包括已安装 UI 示例。
- live 备份不含真实音频（没有调用真实供应商）；音频／信任／后端文件恢复另由模拟素材 fixture 测试覆盖。

## 5. 尚未验证，不作成功声明

1. Gemini / OpenAI 兼容决策 / TTS 的真实联网、模型支持、配额、听感和音频解码；没有真实密钥。
2. 人耳听到的浏览器中文 voice；测试使用 stub，用户设备可能没有可用声线。
3. 在线插件市场与 GitHub CI 的运行结果不由本地测试证明；项目上传／测试版 Release 的结果以仓库页面为准。
4. Docker 镜像构建、真实域名 TLS、公网压测、恶意客户端全面渗透、费用硬额度和 SLA。
5. 多 worker / 多机器、持久任务队列、供应商 exactly-once、音频 GC／配额、完整规则／战棋与语音会议。

Python 后端需要人工信任，不是任意代码安全沙箱。外部调用可能已收费而结果被关闭／回档／冲突拒绝；哈希与数据库幂等不保证付费网络事务可撤销。当前交付是小团体可运行模块化 MVP 与生态基础。
