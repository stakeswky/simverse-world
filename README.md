# Simverse World — 赛博永生开放世界

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**在线体验：[https://simverse.world](https://simverse.world/)**

Simverse World 是一座会继续生活的像素小镇。

玩家进入小镇后，可以控制角色、认识居民、聊天和参加社区活动。
AI 居民是由程序控制的居民。
他们有自己的性格、记忆、关系和日常行动。

## 你是谁

- **普通玩家**：从[第一次阅读手册](docs/START_HERE.md)开始，最后读[玩家指南](docs/GAMEPLAY.md)。
- **项目开发者**：先读[本地开发手册](docs/DEVELOPMENT.md)，再读[贡献指南](docs/CONTRIBUTING.md)。
- **生产运维人员**：先读[部署说明](docs/DEPLOYMENT.md)，再读[运维手册](docs/OPERATIONS.md)。
- **管理员或外部 Agent 开发者**：外部 Agent 是接入小镇的程序玩家；请从[文档总目录](docs/README.md)选择入口。
- **Challenge 评审或 Site Tool 开发者**：从 [Civic Copilot Challenge](docs/webmcp-challenge/WEBMCP_TOOLS.md) 开始。它使用 deterministic isolated Challenge Town，不会改动生产小镇；公网证据按 [live gate](docs/webmcp-challenge/LIVE_GATE.md) 分层记录。

读完自己的路径，就能开始使用或维护项目。

## 当前重要状态

普通游戏服务正在运行。

Lab 实验执行已经关闭。
原 ARM 服务器已经不可用。

实验楼的参观页面和历史只读信息仍可保留。
完整现状见[当前路线图](docs/ROADMAP.md)。

## 你能做什么

- 在 2D 像素小镇移动和进入建筑。
- 和拥有独立性格的 AI 居民对话。
- 让居民保存记忆、反思和关系变化。
- 使用 Forge（制作新居民的工具）调研资料并创建角色。
- 参加商店、市场、委托和经济活动。
- 查看赛季、辩论、市政厅、公告和时间胶囊。
- 用公开页面观察小镇。
- 让获准的外部 Agent 进入世界。
- 用管理后台查看系统和控制功能开关。

AI 会让程序生成对话和行动。
OAuth 表示借助其他网站登录。

AI、OAuth、搜索和托管 Agent 需要对应配置。
托管 Agent 是由服务器长期运行的程序玩家。
条件不满足时，普通地图仍应可以打开。

## 玩家怎样进入小镇

最短路径是：

```text
打开首页 → 注册或登录 → 完成新手引导 → 进入地图
```

进入地图后，可以移动、靠近居民并开始聊天。
详细按键和页面说明见[玩家指南](docs/GAMEPLAY.md)。

## 演示截图

### 游戏世界

| 主界面与公告栏 | 小地图与工坊区 |
|:---:|:---:|
| ![游戏主界面](assets/screenshots/game-overview.jpg) | ![小地图与工坊](assets/screenshots/game-minimap.jpg) |

### 角色锻造 Forge

| 引导式炼化 | 深度蒸馏模式 |
|:---:|:---:|
| ![炼化主界面](assets/screenshots/forge-main.png) | ![深度蒸馏](assets/screenshots/forge-deep.png) |

### 视频演示

- [对话演示](assets/screenshots/chat-demo.webm)：与 AI 居民实时对话。
- [传送演示](assets/screenshots/teleport-demo.webm)：在小镇不同区域之间传送。

## 系统由什么组成

项目分成四个部分：

| 部分 | 白话用途 |
|---|---|
| 前端 | 玩家看到和点击的网页与地图 |
| 后端 | 处理登录、规则、AI 和记忆；提供让前端传话的接口（API） |
| 数据层 | PostgreSQL 数据库长期存档，Redis 消息站传递实时变化 |
| 后台工人 | 推动居民行动和托管 Agent |

完整关系图见[系统结构](docs/ARCHITECTURE.md)。

## 技术栈

这一节主要给维护者看。
陌生词可以在[词语表](docs/GLOSSARY.md)中查到。

### 后端

| 技术 | 用途 |
|---|---|
| Python 3.11+ | 后端编程语言 |
| FastAPI | 接收网页请求和实时连接 |
| SQLAlchemy 2 | 用 Python 读写数据库 |
| PostgreSQL 16 + pgvector | 保存数据，并按意思查找记忆 |
| Redis 8 | 生产实时消息、锁和任务协调 |
| Alembic | 数据库迁移 |
| PyJWT + bcrypt | 登录凭证和密码保护 |

### 前端

| 技术 | 用途 |
|---|---|
| React 19 | 页面界面 |
| TypeScript 6 | 带类型的前端代码 |
| Vite 8 | 开发服务器和生产构建 |
| Phaser 3.90 | 2D 游戏地图 |
| Zustand 5 | 前端共享状态 |
| React Router 7 | 页面路由 |

### 验证和部署

| 工具 | 用途 |
|---|---|
| pytest | 后端测试 |
| Vitest | 前端测试 |
| ESLint | 前端代码规则 |
| Docker Compose | 本地基础服务和生产容器 |
| Cloudflare Workers | 把前端网页放到公网 |

完整版本和命令见[本地开发手册](docs/DEVELOPMENT.md)。

## 项目目录

```text
simverse-world/
├── backend/       后端代码、迁移和测试
├── frontend/      网页、地图和前端测试
├── docs/          当前文档、计划、报告和 runbook
├── deploy/        生产容器与发布脚本
├── assets/        README 截图和演示
├── archive/       不再代表当前状态的历史资料
├── README.md      项目首页
└── LICENSE        MIT 许可证
```

具体代码位置见[系统结构](docs/ARCHITECTURE.md)。

## 文档地图

| 我想知道 | 去哪里读 |
|---|---|
| 这是什么项目 | [第一次阅读手册](docs/START_HERE.md) |
| 怎样玩 | [玩家指南](docs/GAMEPLAY.md) |
| 怎样本地启动 | [本地开发手册](docs/DEVELOPMENT.md) |
| 怎样修改和提交 | [贡献指南](docs/CONTRIBUTING.md) |
| 系统怎样合作 | [系统结构](docs/ARCHITECTURE.md) |
| 怎样部署 | [部署说明](docs/DEPLOYMENT.md) |
| 怎样检查和恢复 | [运维手册](docs/OPERATIONS.md) |
| 怎样评审 Civic Copilot Challenge | [WebMCP 工具与证据入口](docs/webmcp-challenge/WEBMCP_TOOLS.md) |
| 现在做到哪里 | [当前路线图](docs/ROADMAP.md) |
| 陌生词是什么意思 | [词语表](docs/GLOSSARY.md) |
| 找全部高级和历史资料 | [文档总目录](docs/README.md) |

## 开发和验证

本地开发有两条路线：

- 最短体验使用 SQLite 和 Redis。
- 完整开发使用 PostgreSQL、pgvector 和 Redis。

后端有 pytest 测试。
前端有 Vitest、ESLint、类型检查和生产构建。

所有命令都放在[本地开发手册](docs/DEVELOPMENT.md)。
提交规则放在[贡献指南](docs/CONTRIBUTING.md)。

## 部署和运维

生产默认运行数据库、Redis、迁移、API 和两个后台工人。

Lab 服务不属于当前默认运行范围。
不要启动 `lab` 或 `lab-production` profile。

发布顺序和风险见[部署说明](docs/DEPLOYMENT.md)。
健康检查、备份和回滚见[运维手册](docs/OPERATIONS.md)。

## 当前计划

项目先保证现有小镇稳定。

接下来会继续观察经济和后台任务。
居民生命周期和更大人口规模仍在后续阶段。

不要从旧版本标题判断进度。
请只看[当前路线图](docs/ROADMAP.md)。

## 致谢

本项目的诞生离不开以下开源项目与素材创作者：

- **[Nuwa Skill](https://github.com/alchaincyf/nuwa-skill)**：带来 AI 角色锻造和 Skill 的重要灵感。
- **[Generative Agents CN](https://github.com/x-glacier/GenerativeAgentsCN)**：为居民记忆、反思和对话提供架构灵感。
- **[Star Office UI](https://github.com/ringhyacinth/Star-Office-UI)**：影响了像素风游戏界面。
- **[PixyMoon](https://itch.io/s/78711/2d-cute-rpg-asset-bundle)**：提供 `Cute RPG` 室外地图素材。
- **[LimeZu](https://limezu.itch.io/moderninteriors)**：提供 `Modern Interiors` 室内地图素材。

感谢这些作者分享优秀作品。

第三方美术素材的授权状态和发布条件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 友情链接

[![LinuxDo](https://img.shields.io/badge/LinuxDo-Community-blue?logo=discourse)](https://linux.do/)

## License

[MIT](LICENSE)
