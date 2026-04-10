# Skills World — 赛博永生开放世界

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**在线体验：[https://simverse.world](https://simverse.world/)**

Skills World 是一个赛博朋克风格的开放世界多人游戏/模拟平台。玩家在像素风的虚拟村落中控制角色（"居民"），与 AI 驱动的 NPC 对话、锻造物品、交易和互动。每个 NPC 拥有独立的灵魂档案，由 LLM 驱动的对话系统赋予其独特的个性和记忆。

## 演示截图

### 游戏世界

| 主界面 & 公告栏 | 小地图 & 工坊区 |
|:---:|:---:|
| ![游戏主界面](docs/screenshots/game-overview.jpg) | ![小地图与工坊](docs/screenshots/game-minimap.jpg) |

### 角色锻造（Forge）

| 引导式炼化 | 深度蒸馏模式 |
|:---:|:---:|
| ![炼化主界面](docs/screenshots/forge-main.png) | ![深度蒸馏](docs/screenshots/forge-deep.png) |

### 视频演示

- [对话演示](docs/screenshots/chat-demo.webm) — 与 AI 角色实时对话
- [传送演示](docs/screenshots/teleport-demo.webm) — 在游戏世界中传送到不同区域

## 核心功能

- **AI 驱动的角色对话** — 基于 LLM 的 NPC 系统，每个角色拥有独立的灵魂（persona / soul / ability）
- **角色锻造（Forge）** — 多阶段 pipeline：自动调研 → 信息提取 → 角色构建 → 验证 → 精炼
- **2D 像素风游戏世界** — Phaser.js 等距视角，小地图、角色移动、NPC 状态可视化
- **AI 头像生成** — 通过 Gemini 模型自动生成角色像素风头像
- **管理后台** — 系统配置、仪表盘、居民管理、经济系统、服务健康监控
- **OAuth 登录** — 支持 LinuxDo / GitHub OAuth
- **WebSocket 实时通信** — 游戏状态同步、聊天、NPC 行为广播

## 技术栈

### 后端

| 技术 | 用途 |
|------|------|
| [FastAPI](https://fastapi.tiangolo.com/) | Web 框架 & REST API |
| [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (async) | ORM |
| [PostgreSQL](https://www.postgresql.org/) 16 | 主数据库（开发可用 SQLite） |
| [Redis](https://redis.io/) 7 | 缓存 & 会话 |
| [Alembic](https://alembic.sqlalchemy.org/) | 数据库迁移 |
| [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) | LLM 调用（兼容 OpenAI 格式端点） |
| [httpx](https://www.python-httpx.org/) | 异步 HTTP 客户端 |
| [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | 配置管理 |
| [python-jose](https://github.com/mpdavis/python-jose) + [Passlib](https://passlib.readthedocs.io/) | JWT 认证 & 密码哈希 |

### 前端

| 技术 | 用途 |
|------|------|
| [React](https://react.dev/) 19 | UI 框架 |
| [TypeScript](https://www.typescriptlang.org/) 6 | 类型安全 |
| [Vite](https://vite.dev/) 8 | 构建工具 & 开发服务器 |
| [Phaser.js](https://phaser.io/) 3.90 | 2D 游戏引擎 |
| [Zustand](https://zustand.docs.pmnd.rs/) 5 | 状态管理 |
| [React Router](https://reactrouter.com/) 7 | 路由 |

### 基础设施

| 技术 | 用途 |
|------|------|
| [Docker](https://www.docker.com/) + Docker Compose | 容器化部署 |
| [Cloudflare Workers](https://workers.cloudflare.com/) | 前端静态站点部署（可选） |
| [SearXNG](https://docs.searxng.org/) | 自建搜索引擎（角色调研用） |

## 项目结构

```
Skills-World/
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── config.py         # Pydantic Settings 配置中心
│   │   ├── main.py           # FastAPI 入口 & 路由注册
│   │   ├── database.py       # 数据库引擎 & Session
│   │   ├── models/           # SQLAlchemy ORM 模型
│   │   ├── routers/          # API 路由
│   │   │   ├── auth.py       #   注册 / 登录 / JWT
│   │   │   ├── residents.py  #   角色（居民）CRUD
│   │   │   ├── forge.py      #   锻造 API
│   │   │   ├── profile.py    #   用户档案
│   │   │   └── admin/        #   管理后台 API
│   │   ├── services/         # 业务逻辑
│   │   │   ├── portrait_service.py  # AI 头像生成
│   │   │   └── linuxdo_auth.py      # LinuxDo OAuth
│   │   ├── forge/            # 角色锻造 pipeline
│   │   │   ├── pipeline.py   #   主流程编排
│   │   │   ├── research_stage.py    # SearXNG 调研
│   │   │   ├── extraction_stage.py  # LLM 信息提取
│   │   │   ├── build_stage.py       # 角色构建
│   │   │   ├── validation_stage.py  # 质量验证
│   │   │   └── refinement_stage.py  # 精炼优化
│   │   ├── llm/              # LLM 客户端工厂
│   │   ├── ws/               # WebSocket 处理
│   │   └── tasks/            # 定时任务（热度计算等）
│   ├── alembic/              # 数据库迁移脚本
│   ├── tests/                # pytest 测试
│   └── seed/                 # 初始数据种子脚本
├── frontend/                 # React + Phaser.js 前端
│   ├── src/
│   │   ├── components/       # React 组件（管理面板、游戏 UI 等）
│   │   ├── game/             # Phaser 游戏场景 & 精灵
│   │   ├── pages/            # 页面组件
│   │   ├── stores/           # Zustand 状态管理
│   │   └── services/         # API 客户端封装
│   └── public/               # 静态资源（地图、精灵图等）
├── deploy/                   # 部署配置
│   ├── backend/              #   Docker + deploy 脚本
│   └── frontend/             #   Cloudflare Workers 配置
├── docs/screenshots/         # 演示截图 & 视频
├── docker-compose.yml        # 本地开发基础设施
└── LICENSE                   # MIT License
```

---

## 部署方式一：本地开发（直接部署）

适用于开发调试，不需要 Docker 构建镜像，直接运行 Python 和 Node.js。

### 前置要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 16（或使用 SQLite 开发模式）
- Redis 7（可选，热度计算等功能需要）

### Step 1：启动数据库和 Redis

**方式 A：使用 Docker 启动基础设施（推荐）**

```bash
# 在项目根目录
docker compose up -d
```

这会启动 PostgreSQL（端口 5432）和 Redis（端口 6379）。

**方式 B：使用系统已有的 PostgreSQL / Redis**

确保 PostgreSQL 和 Redis 已运行，后续在 `.env` 中配置连接地址即可。

**方式 C：纯 SQLite 模式（最简单）**

不需要 PostgreSQL 和 Redis，在 `.env` 中设置：

```bash
DATABASE_URL=sqlite+aiosqlite:///./skills_world_dev.db
```

### Step 2：启动后端

```bash
cd backend

# 复制环境变量模板并填写
cp .env.example .env
```

编辑 `backend/.env`，至少填写以下内容：

```bash
# 数据库（二选一）
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/skills_world
# DATABASE_URL=sqlite+aiosqlite:///./skills_world_dev.db

# Redis（可选）
REDIS_URL=redis://localhost:6379/0

# JWT 密钥（开发环境随意，生产必须用长随机字符串）
JWT_SECRET=my-dev-secret

# LLM API（必填，支持任何 Anthropic SDK 兼容的端点）
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://api.anthropic.com          # 或其他兼容端点
LLM_MODEL=claude-haiku-4-5-20251001

# SearXNG 搜索引擎（角色锻造调研用，可选）
SEARXNG_URL=http://localhost:58080
```

然后：

```bash
# 安装依赖
pip install -e ".[dev]"

# 执行数据库迁移
alembic upgrade head

# 导入初始居民数据（可选）
python3 -m seed.seed_residents

# 启动后端
uvicorn app.main:app --reload --port 8000
```

后端运行于 http://localhost:8000，API 文档：http://localhost:8000/docs

### Step 3：启动前端

```bash
cd frontend

# 复制环境变量
cp .env.example .env
# 默认 VITE_API_URL=http://localhost:8000，通常无需修改

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端运行于 http://localhost:5173

### 验证

- 打开 http://localhost:5173 应看到游戏界面
- 访问 http://localhost:8000/health 应返回 `{"status": "ok"}`
- 访问 http://localhost:8000/docs 查看 API 文档

---

## 部署方式二：Docker 部署（生产环境）

适用于服务器部署，使用 Docker Compose 一键启动后端 + 数据库。

### 前置要求

- 一台 Linux 服务器（推荐 Ubuntu 22.04+）
- Docker 24+ & Docker Compose v2
- Node.js 18+（用于构建前端）

### Step 1：准备后端

```bash
cd deploy/backend

# 复制并编辑环境变量
cp .env.example .env
```

编辑 `deploy/backend/.env`：

```bash
# PostgreSQL 密码（会被 docker-compose 使用）
POSTGRES_PASSWORD=你的强密码

# JWT 密钥（生成方式：openssl rand -hex 32）
JWT_SECRET=生成的64字符随机字符串

# LLM API
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://api.anthropic.com
LLM_MODEL=claude-haiku-4-5-20251001

# SearXNG（如果部署了搜索引擎）
SEARXNG_URL=http://your-searxng-host:58080

# AI 头像生成（可选）
PORTRAIT_LLM_MODEL=gemini-3-pro-image-preview
PORTRAIT_LLM_BASE_URL=http://your-gemini-proxy:3000/v1
PORTRAIT_LLM_API_KEY=sk-your-portrait-key

# CORS — 设置为你的前端域名
CORS_ORIGINS=["https://your-domain.com"]

# LinuxDo OAuth（可选）
LINUXDO_CLIENT_ID=
LINUXDO_CLIENT_SECRET=
LINUXDO_REDIRECT_URI=
```

### Step 2：启动后端服务

```bash
cd deploy/backend
docker compose up -d --build
```

这会启动：
- **PostgreSQL 16** — 数据库（仅监听 127.0.0.1:5432）
- **API 服务** — FastAPI 应用（监听 0.0.0.0:8100）

验证：

```bash
curl http://localhost:8100/health
# 应返回 {"status": "ok"}
```

### Step 3：构建并部署前端

**方式 A：Cloudflare Workers（推荐）**

```bash
cd frontend

# 设置 API 地址为你的后端域名
echo "VITE_API_URL=https://api.your-domain.com" > .env

# 构建
npm install
npm run build

# 部署到 Cloudflare Workers
npx wrangler deploy
```

如需绑定自定义域名，编辑 `deploy/frontend/wrangler.toml`：

```toml
routes = [
  { pattern = "your-domain.com", custom_domain = true }
]
```

**方式 B：Nginx 静态托管**

```bash
cd frontend

echo "VITE_API_URL=https://api.your-domain.com" > .env
npm install
npm run build
```

将 `frontend/dist/` 目录部署到 Nginx：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /var/www/skills-world/dist;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 反向代理 API
    location /api/ {
        proxy_pass http://127.0.0.1:8100/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:8100/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Step 4：远程部署（可选快捷脚本）

如果你想从本地一键部署到远程服务器：

```bash
cd deploy/backend
./deploy.sh user@your-server-ip
```

该脚本会通过 SSH + rsync 同步代码，然后在远程执行 `docker compose up -d --build`。

---

## 部署方式三：Docker 全栈部署

如果你希望前后端都通过 Docker 运行，可以在项目根目录创建一个全栈 compose 文件，或在 Nginx 容器中挂载前端构建产物。以下是一个参考配置：

```yaml
# docker-compose.prod.yml（参考，需根据实际情况调整）
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: skills_world
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"

  api:
    build:
      context: ./backend
      dockerfile: ../deploy/backend/Dockerfile
    restart: unless-stopped
    ports:
      - "127.0.0.1:8100:8000"
    depends_on:
      - db
    env_file: ./deploy/backend/.env
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@db:5432/skills_world

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./frontend/dist:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - api

volumes:
  pgdata:
```

---

## 环境变量参考

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `DATABASE_URL` | 是 | `postgresql+asyncpg://...` | 数据库连接字符串 |
| `REDIS_URL` | 否 | `redis://localhost:6379/0` | Redis 连接字符串 |
| `JWT_SECRET` | 是 | — | JWT 签名密钥 |
| `LLM_API_KEY` | 是 | — | LLM API 密钥 |
| `LLM_BASE_URL` | 否 | — | 自定义 LLM 端点（留空则使用 Anthropic 官方） |
| `LLM_MODEL` | 否 | `claude-haiku-4-5-20251001` | 默认 LLM 模型 |
| `LLM_MAX_TOKENS` | 否 | `512` | 单次 LLM 最大 token 数 |
| `SEARXNG_URL` | 否 | `http://localhost:58080` | SearXNG 搜索引擎地址 |
| `PORTRAIT_LLM_BASE_URL` | 否 | — | 头像生成 API 地址 |
| `PORTRAIT_LLM_API_KEY` | 否 | — | 头像生成 API 密钥 |
| `PORTRAIT_LLM_MODEL` | 否 | `gemini-3-pro-image-preview` | 头像生成模型 |
| `CORS_ORIGINS` | 否 | `["http://localhost:5173"]` | 允许的跨域来源（JSON 数组） |
| `LINUXDO_CLIENT_ID` | 否 | — | LinuxDo OAuth Client ID |
| `LINUXDO_CLIENT_SECRET` | 否 | — | LinuxDo OAuth Client Secret |
| `GITHUB_CLIENT_ID` | 否 | — | GitHub OAuth Client ID |

## 开发指南

### 运行测试

```bash
# 后端测试
cd backend
python3 -m pytest tests/

# 前端类型检查
cd frontend
npx tsc --noEmit
```

### 数据库迁移

```bash
cd backend

# 生成新迁移
alembic revision --autogenerate -m "add xxx table"

# 执行迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1
```

### LLM 兼容性

后端通过 Anthropic SDK 调用 LLM，支持任何兼容 Anthropic Messages API 格式的端点：

- [Anthropic Claude](https://docs.anthropic.com/) — 官方端点
- [DashScope](https://dashscope.aliyuncs.com/) — 阿里云百炼（兼容模式）
- 其他兼容 OpenAI / Anthropic 格式的代理

只需在 `.env` 中设置 `LLM_BASE_URL` 和 `LLM_API_KEY` 即可切换。

## Roadmap

### v1.1 — 角色增强

- [ ] AI 头像生成集成到锻造流程（portrait_service 已实现，待接入创建链路）
- [ ] 角色版本管理 — 支持回滚到历史版本的灵魂档案
- [ ] 自定义 LLM 提供商 — 用户可配置自己的 API Key 和模型偏好
- [ ] NPC 回复模式 — 支持手动/自动/定时回复策略

### v1.2 — 社交与经济

- [ ] 玩家间私聊系统
- [ ] 物品与背包系统 — 可交易的虚拟物品
- [ ] 交易市场 — 玩家之间的物品/Soul Coin 交易
- [ ] 好友系统与关注列表
- [ ] 公会/社团 — 玩家自建组织

### v1.3 — 世界演化

- [ ] NPC 自主行为 — 路径规划、自主移动、NPC 之间对话
- [ ] 昼夜循环与天气系统
- [ ] 区域专属机制 — 不同区（工坊/学院/自由区）拥有独特玩法
- [ ] 世界事件系统 — 全服事件触发与参与

### v1.4 — 平台扩展

- [ ] GitHub OAuth 完善
- [ ] 移动端适配（响应式 UI + 触控操作）
- [ ] 国际化（i18n）支持
- [ ] 开放 API — 第三方可接入自定义角色和技能

### 远期愿景

- 居民之间自发形成社区与文化
- 基于对话记忆的长期关系演化
- 用户自建区域与建筑
- AI 驱动的经济系统自平衡

## 致谢

本项目的诞生离不开以下开源项目的启发与贡献，在此致以诚挚的感谢：

- **[Nuwa Skill](https://github.com/alchaincyf/nuwa-skill)** — AI 角色锻造的核心灵感来源。Nuwa 的 Skill 概念和 LLM 驱动的角色构建思路深刻影响了本项目的 Forge pipeline 设计。
- **[Generative Agents CN](https://github.com/x-glacier/GenerativeAgentsCN)** — 斯坦福「生成式智能体」论文的中文复现。本项目的 AI 居民行为系统（记忆、反思、对话）从中汲取了大量灵感和架构思路。
- **[Star Office UI](https://github.com/ringhyacinth/Star-Office-UI)** — 精美的像素风 UI 资源包。本项目的游戏界面视觉风格和部分精灵素材源自此项目。

感谢这些项目的作者们将优秀的工作开源分享，让更多人能够站在巨人的肩膀上创造新的可能。

## License

[MIT](LICENSE)
