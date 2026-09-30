# 余烬酒馆 · Ember Tavern

一个**真正可运行**的轻量多人 AI 跑团 MVP：账号、邀请码房间、角色分配、世界书、服务端骰子、双模型接口、事件快照、回档与当前时间线检索。

> 默认是明确标注的**演示规则脚本**，不是 Gemini 或其他真实 AI 回复。Gemini 原生接口和 OpenAI 兼容决策接口已实现并通过模拟服务契约测试；你需要自己的合法 API 凭证，完成实际联网与效果验收。

## 1. 先试玩，再改代码

### 方法 A：使用已打包的前端（不需要 Node）

要求 Python 3.11+。本次验证环境为 Python 3.13、Node 20。

```bash
cd ember-tavern
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 改为：.venv\Scripts\Activate.ps1

pip install -r requirements.txt
# 如需完全采用本次验证版本：pip install -r requirements-lock.txt
cp .env.example .env
# Windows 可使用：Copy-Item .env.example .env

python -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 65536
```

打开 `http://localhost:8000`。**不要直接双击 static/index.html**：账号和游戏状态需要后端服务。

首次运行自动创建 `data/tavern.sqlite3`；状态存放在数据库里，刷新或重启不会清空。

### 五分钟试玩路径

1. 点击“走进酒馆 · 免费试玩”，立即得到一个体验房间。
2. 描述行动，如“我仔细检查这枚黄铜钥匙”。
3. 出现检定卡片后点击“掷 d20”，观察服务器记录的结果。
4. 到角色档案查看生命、压力与物品。
5. 到事件档案选择历史节点回档，观察状态恢复与后续记录封存。

体验账号没有可找回的密码，退出后不保证能再次登录原账号。**正式多人测试请注册账号。**

### 两人一起玩

- A 注册账号、创建房间，在“邀请同伴”复制邀请码或邀请链接。
- B 在自己的浏览器/独立浏览器配置中注册，使用邀请码加入。
- A 在角色档案的操控者下拉框中把角色分配给 B。
- B 提交角色行动，A 应无需刷新即可看到行动、检定和新状态。
- 使用同一机器测试时，请用两个独立浏览器上下文或普通窗口 + 无痕窗口。登录令牌存放在本标签页的 sessionStorage，避免不同身份相互覆盖。

同一局域网可使用服务器的 LAN IP 加端口访问。跨互联网需要服务器、HTTPS、域名/反向代理与安全加固；当前临时预览不是你的永久托管地址。

## 2. 真实双模型配置

只在服务器根目录 `.env` 设置，**不要发到聊天、放进前端或提交到 Git**：

```dotenv
GEMINI_API_KEY=你的Gemini密钥
GEMINI_MODEL=你的账户实际可用模型ID

DECISION_BASE_URL=https://你的服务商地址/v1
DECISION_API_KEY=你的决策模型密钥
DECISION_MODEL=服务商实际支持的模型ID
DECISION_JSON_MODE=true
AI_TIMEOUT_SECONDS=45
```

重启后端，使用**正式注册账号**，在“主持设置”切换“真实双模型主持”，或创建时选真实模式。

- Gemini：原生 `POST /v1beta/models/{model}:generateContent`，密钥使用请求头。
- 决策模型：`POST {DECISION_BASE_URL}/chat/completions`，OpenAI 兼容结构。
- 部分兼容服务不支持 `response_format`，将 `DECISION_JSON_MODE=false`。服务器仍验证 JSON Schema。
- “jev”名称未明确，不对其身份或协议作假设。如不兼容该协议，需要新增适配器。
- 界面“已配置”不表示密钥或模型已经联网验证；错误会保留原行动/骰子并允许房主重试或人工补述。
- **不会静默从真实模型降级为演示回复。**

### 调用成本要知道

当前每次主持是两次串行模型调用。有检定的一轮通常是四次（行动后二次、骰后二次）；重试也可能收费。每个接口默认 45 秒超时。尚无 token 精确预算、费用账本或部署级硬限额，请先在私人、受控的测试环境接入付费密钥。

## 3. 修改前端

```bash
cd web
npm ci
npm run build
```

构建输出到项目根 `static/`，由 FastAPI 同源服务提供。交付包已包含这一目录，后端运行无需先构建。

开发时：后端运行在 8000，前端运行 `npm run dev`（通常 5173）。Vite 把 `/api` 和 `/ws` 代理到后端；浏览器代码不直接调用 localhost 后端地址。

所有图片、样式、图标都在本地；没有外部 CDN 字体依赖。背景图是 AI 生成的项目资产，不是 SillyTavern 截图。

## 4. 测试

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

测试覆盖权限、骰子、模型响应约束、并发、幂等、WebSocket、持久化、回档恢复、检索隔离与敏感字段不导出。模型外部服务使用 HTTPX 模拟，不消耗真实 API 额度。

可选浏览器端测试（需要先启动 8000 服务）：

```bash
python -m playwright install --with-deps chromium
python tests/browser_smoke.py
```

详细结果与尚未验收项见 [测试报告](docs/TEST_REPORT.md)。浏览器测试会创建独立测试账号与房间，建议在测试数据库运行。

## 5. Docker 单机部署

```bash
cp .env.example .env
# 按需填写模型配置

docker compose up --build -d
```

默认端口 8000，数据库存放在名为 `tavern-data` 的持久卷。Dockerfile 会从源码构建前端。

- **只运行 1 个 worker。** 房间锁、广播和限速是进程内的；多进程/多节点扩容前需要 Redis 等共享基础设施。
- 不要删除持久数据卷，否则游戏数据会消失。
- 云服务器提供商必须支持 WebSocket 长连接。
- 正式跨互联网部署用 Caddy/Nginx 提供 HTTPS 和访问策略；可参考 `deploy/Caddyfile.example`。
- Docker 配置在本次交付中提供，但当前环境未执行 Docker 镜像构建；Python 直接运行已验证。

### SQLite 在线备份

```bash
python scripts/backup.py
# 或指定输出文件
python scripts/backup.py --output backups/my-session.sqlite3
```

脚本使用 SQLite backup API，适合 WAL 模式；不要在服务写入时仅复制主 `.sqlite3` 文件。备份包含账号与游戏数据，应按敏感数据存放。

恢复：**先停服务**，备份当前数据目录，将备份文件恢复为 `DATA_DIR/tavern.sqlite3`，清理停服后的旧 `-wal/-shm` 文件，再启动。务必先在测试环境演练。JSON 导出是会话档案，首版未实现 JSON 导入。

## 6. 项目结构

```text
server/
  app.py         REST、WebSocket、权限、并发与回档
  auth.py        scrypt 密码、随机会话令牌
  db.py          SQLite 表、事务、事件与快照
  domain.py      轻规则、角色、预设、服务端骰子
  schemas.py     输入与决策输出约束
  retrieval.py   当前房内有效时间线关键词检索
  ai.py          Gemini / OpenAI 兼容适配器与明确的演示脚本
web/src/         React 界面、同源 API 客户端与样式
web/public/      项目本地图片与图标
static/          可直接服务的预构建前端
tests/           后端与可选浏览器测试
docs/            PRD 与测试报告
scripts/         启动、数据库备份
Dockerfile / compose.yaml / .env.example
```

API 文档：运行后访问 `/docs`。健康检查：`/api/health`。

## 7. 重要边界

这是朋友间小规模可玩的 MVP，**不是完整 VTT 或已完成公开商业上线的系统**。

已支持：轻规则、世界书、角色状态、多人同步、服务端骰子、结构化主持、快照回档。

尚未支持：完整 D&D/CoC 规则、地图战棋、语音、主持秘密区、踢人/撤销邀请码、密码找回、向量记忆、JSON 导入、多节点、付费配额。

回档恢复叙事状态，不回退账号、成员、操控权限、模型运行模式或已处理请求 ID。被封存的未来不进入当前模型上下文。

Bearer 令牌存放在 sessionStorage，仍需防 XSS；公开上线前补齐鉴权、限额、HTTPS、监控、备份和安全审计。当前有基础进程内限速，但没有公开注册场景下的消费硬上限。请勿直接把接有付费密钥的服务开放给不受信任用户。

完整产品边界、规则、验收标准与路线见 [PRD](docs/PRD.md)。
