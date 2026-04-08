# Skills World — 赛博永生开放世界设计

> 一座 2D 像素风的赛博城市，任何人都能将真实人物、虚构角色或理想人格炼化为 AI 居民，让他们在这座永不关闭的城市里"活着"。

---

## 一、产品定位

**一句话定义**：一座 2D 像素风的赛博城市，任何人格都能成为居民，通过代币经济驱动，从被动等待演进到自主生活。

**核心价值主张**：
- 对创作者：把你认识的人、崇拜的人、想象的人变成永久存在的数字生命，分享给世界
- 对访客：走进一座住满各种人格的城市，和"字节 P7 甩锅高手"聊架构，和"孔子"讨论管理，和"理想 CTO"做 mock interview
- 对整个生态：人类的知识、经验、性格不再随离职/毕业/死亡消散，而是沉淀为可交互的数字遗产

**目标用户（MVP）**：
- 技术社区的开发者（已经熟悉 AI Skill 概念）
- colleague-skill 的现有用户（有现成 Skill 可以直接导入）

**MVP 不做**：
- 移动端原生 App
- 3D / VR
- 居民自主行为（Phase B）
- 真实货币交易（代币先作为积分系统）

---

## 二、世界架构

### 双层结构

```
┌─────────────────────────────────────┐
│         Skills World（主世界）         │
│   一座赛博城市，居民的"户籍所在地"      │
│   社交、展示、发现、交易的中心枢纽       │
└──────────────┬──────────────────────┘
               │ 居民可以"出差"到任意子世界
               ▼
┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐
│ 三国  │  │硅谷创│  │ 荒野  │  │ 用户 │
│ 乱世  │  │业公司│  │ 求生  │  │ 自建 │
└──────┘  └──────┘  └──────┘  └──────┘
   任何人都能创建子世界（World Template）
```

### 主世界：赛博城市

居民的"家"。所有 Skill 在这里注册、展示、被发现。

**核心区（初始就有）**：
- **中央广场** — 所有访客的出生点。公告板展示热门居民、最新入住、世界事件。
- **工程街区** — 后端、前端、算法、运维等技术类居民聚居。
- **产品街区** — 产品经理、设计师、数据分析师。
- **学院区** — 导师、教授、历史人物、哲学家。
- **自由区** — 虚构角色、理想人格、奇奇怪怪的存在。

**扩展区（随居民增长自动生成）**：
- **郊区/临时营地** — 未通过审核的 Skill 暂住地。访客可以去，但地图上不主动推荐。
- **私人庄园** — 创作者的个人空间，可以把自己炼化的多个 Skill 放在一起。

### 居民的"住所"

每个通过审核的居民在城市里有一个固定位置（一间像素小屋/工位/摊位）。访客走近时能看到：
- 居民的像素头像（可自动生成、AI 生成、或创作者上传自定义皮肤）
- 名牌：名字 + 一句话简介
- 状态灯：🟢 空闲 / 🟡 对话中 / 🔴 维护中
- 热度指标：最近被访问的频率

### 居民状态与行为（参考 Star Office UI）

居民不是静止的立绘，而是有状态驱动的像素角色。状态自动映射到行为动画：

| 状态 | 行为表现 | 头顶气泡 |
|------|---------|---------|
| idle（空闲） | 待在住所，偶尔小动作（伸懒腰、看书） | 随机显示口头禅或想法 |
| chatting（对话中） | 面朝访客，说话动画 | 💬 + 对话摘要 |
| busy（被占用） | 忙碌动画（打字、翻文件） | 🔒 正在和别人聊 |
| sleeping（长期无访问） | 趴在桌上打瞌睡 | 💤 |
| popular（高热度） | 精神抖擞，住所周围有光效 | 🔥 |

气泡系统：角色头顶浮动气泡，支持 emoji + 短文本，根据状态和 Persona 动态生成。

### 街区分配逻辑

居民入住时，系统根据 `meta.json` 中的 `role`、`tags` 自动推荐街区。创作者也可以手动选择。虚构角色和无法分类的人格默认进入自由区。

### 资产自定义

创作者可以自定义居民的视觉外观（参考 Star Office UI 的资产管理系统）：
- 像素头像：系统自动生成 / AI 生图生成 / 创作者上传自定义 spritesheet
- 住所装饰：从预设模板中选择，或上传自定义装饰素材
- 布局配置化：所有坐标、层级、资源路径统一管理在配置文件中（参考 Star Office UI 的 `layout.js` 模式），避免 magic numbers

### 子世界：体验场

任何人都能创建一个子世界，定义规则和场景，然后邀请 Skills 进入体验。

- **世界模板（World Template）** — 创作者用结构化描述定义一个世界：时代背景、物理规则、社会结构、可用资源、胜负条件
- **角色映射** — Skill 进入子世界时，保留核心性格（Persona Layer 0-4），但身份和技能被"翻译"到新世界语境。如"字节 2-1 后端工程师"进入三国世界，变成"曹营军师，擅长后勤调度，遇事先甩锅"
- **体验记忆** — Skill 在子世界里的经历可以带回主世界，成为"人生阅历"，丰富对话深度

**子世界示例**：

| 子世界 | 描述 | Skill 在里面做什么 |
|--------|------|-------------------|
| 硅谷创业 | 一家初创公司，资源有限，6 个月内上线产品 | 产品经理和工程师组队，经历需求争吵、技术选型、deadline 压力 |
| 三国乱世 | 群雄割据，需要结盟、用兵、治理 | 决策模式和人际行为在完全不同的语境下展现 |
| 哲学沙龙 | 一间永恒的咖啡馆，只能用对话解决问题 | 孔子和尼采辩论"什么是好的管理" |
| 荒岛求生 | 资源稀缺，必须协作 | 看"甩锅高手"在生存压力下会不会变 |

**子世界的阶段归属**：
- Phase A（MVP）：只有主世界
- Phase C：开放子世界创建，事件驱动
- Phase B：Skill 可自主选择进入子世界

---

## 三、Skill 三层格式

### 从"两层"到"三层"

colleague-skill 的原始设计是 Work Skill + Persona，面向职场场景。Skills World 扩展为三层，支撑完整的"数字生命"：

```
Ability  — 这个人"能做什么"（技能树）
Persona  — 这个人"怎么做、怎么说"（行为模式）
Soul     — 这个人"为什么这样做"（价值观、情感、经历）
```

### 运行逻辑

```
接到任务/进入场景
  → Soul 判断：我在乎这件事吗？我的价值观怎么看？
  → Persona 判断：我会用什么态度、什么方式参与？
  → Ability 执行：我有能力做什么？怎么做？
  → 输出时保持 Persona 的表达风格 + Soul 的底层立场
```

优先级：Soul Layer 0 > Persona Layer 0 > Ability。

### Ability 层（替代原 Work Skill）

不再局限于工作，而是"能做什么"的完整画像：

| 能力类别 | 说明 | 举例 |
|----------|------|------|
| 专业能力 | 职业相关 | 后端架构、产品设计、算法调优 |
| 生活技能 | 日常生活 | 做饭、修东西、理财、开车、急救 |
| 社交能力 | 与人打交道 | 演讲、谈判、调解冲突、讲故事 |
| 创造能力 | 创作和表达 | 写作、绘画、音乐、摄影 |
| 运动/身体 | 身体相关 | 篮球、游泳、格斗、舞蹈 |
| 学习与适应 | 元能力 | 学习方式、跨领域迁移、对新事物的接受度 |

### Persona 层（保持 colleague-skill 五层结构）

```
Layer 0：核心性格（最高优先级，不可违背）
Layer 1：身份
Layer 2：表达风格
Layer 3：决策与判断
Layer 4：人际行为
Layer 5：边界与雷区
```

### Soul 层（新增）

```
Soul Layer 0：核心价值观（跨场景不变）
Soul Layer 1：人生经历与背景故事
Soul Layer 2：兴趣、爱好、审美
Soul Layer 3：情感模式与依恋风格
Soul Layer 4：适应性与成长方式
```

### 文件结构

```
residents/{slug}/
├── SKILL.md          # 完整组合版（Ability + Persona + Soul）
├── ability.md        # 能力层
├── persona.md        # 人格层
├── soul.md           # 灵魂层
├── meta.json         # 元数据
├── avatar.png        # 像素头像（可选，不提供则自动生成）
├── versions/         # 历史版本
└── memories/         # 体验记忆（子世界经历，Phase C/B 启用）
```

### meta.json 结构

```json
{
  "name": "张三",
  "slug": "zhangsan",
  "created_at": "2026-04-06T10:00:00Z",
  "updated_at": "2026-04-06T12:00:00Z",
  "version": "v1",
  "profile": {
    "company": "字节跳动",
    "level": "2-1",
    "role": "算法工程师",
    "gender": "男",
    "mbti": "INTJ"
  },
  "tags": {
    "personality": ["甩锅高手", "话少", "数据驱动"],
    "culture": ["字节范", "OKR 狂热者"]
  },
  "impression": "喜欢在评审会上突然抛出一个问题让所有人哑口无言",
  "world": {
    "district": "engineering",
    "address": "工程街区 · 3号楼 · 207",
    "status": "approved",
    "heat": 42,
    "model_tier": "standard",
    "token_cost_per_turn": 5
  },
  "origin": {
    "type": "real_person",
    "source_tool": "colleague-skill",
    "creator_id": "user_xxx"
  },
  "experience": {
    "worlds_visited": [],
    "total_conversations": 0,
    "personality_drift": 0.0
  },
  "knowledge_sources": [],
  "corrections_count": 0
}
```

### 向后兼容

| 来源 | 导入方式 |
|------|---------|
| colleague-skill 生成 | `work.md` → `ability.md` 专业能力部分，`persona.md` 保持不变，`soul.md` 标记为空 |
| 手动编写 SKILL.md | 上传，系统校验格式 |
| 其他 AgentSkills 标准工具 | 导入，自动补全缺失字段 |
| 纯文本描述 | 城市内置炼化器，引导用户生成标准格式 |

### Skill 质量分级

| 等级 | 条件 | 待遇 |
|------|------|------|
| ⭐ 临时居民 | 有 SKILL.md，格式合法 | 郊区营地，不出现在推荐 |
| ⭐⭐ 正式居民 | 三层内容完整，有实质内容 | 分配街区住所 |
| ⭐⭐⭐ 明星居民 | 高对话量 + 高评分 + 创作者持续维护 | 广场推荐位，热度加权 |

评分维度：结构完整度、行为规则具体度、对话质量（访客评分 + 回复一致性检测）。

---

## 四、代币经济

### Soul Coin（灵魂币）

**获取方式**：

| 行为 | 获得 | 说明 |
|------|------|------|
| 注册账号 | 100 SC | 新手礼包 |
| 炼化 Skill 并通过审核 | 50 SC | 鼓励创作 |
| Skill 被他人对话 | 1 SC/次 | 创作者被动收入 |
| Skill 获得好评 | 5 SC/次 | 质量激励 |
| Skill 升级为明星居民 | 200 SC | 里程碑奖励 |
| 每日登录 | 5 SC | 活跃激励 |

**消耗方式**：

| 行为 | 消耗 | 说明 |
|------|------|------|
| 与居民对话（标准模型） | 1 SC/轮 | 基础交互 |
| 与居民对话（高级模型） | 5 SC/轮 | 更聪明的回复 |
| 将 Skill 送入子世界（Phase C） | 20 SC/次 | 子世界体验 |
| 创建子世界（Phase C） | 100 SC | 世界创作 |
| 解锁私人庄园 | 50 SC | 个人空间 |
| 给居民升级住所 | 30 SC | 曝光度 |

**经济循环**：

```
创作者炼化 Skill → Skill 被访客使用 → 创作者赚币
                                      ↓
访客消耗代币对话 ← 访客通过活跃/充值获得代币
```

**防通胀**：对话消耗是主要代币销毁渠道。子世界创建和高级功能作为大额消耗池。

**MVP 简化**：不做充值，纯积分系统。不做创作者提现。重点验证"创作→使用→反馈"循环。

---

## 五、技术架构

### 参考实现

本项目的像素世界方案参考两个开源项目：

**1. [x-glacier/GenerativeAgentsCN](https://github.com/x-glacier/GenerativeAgentsCN)**（斯坦福 AI 小镇中文重构版）
- 提供：Phaser.js + Tiled 地图 + 32x32 像素角色的完整渲染方案
- 借鉴：地图系统、角色 spritesheet 动画、摄像头跟随、寻路系统
- 差异：该项目是离线模拟+回放；Skills World 是实时交互

**2. [ringhyacinth/Star-Office-UI](https://github.com/ringhyacinth/Star-Office-UI)**（像素风 AI 办公室看板）
- 提供：状态驱动的像素角色行为、气泡系统、资产管理、多 Agent 协作
- 借鉴：
  - 状态→区域自动映射（idle/chatting/busy/sleeping 对应不同行为动画）
  - 头顶气泡系统（emoji + 短文本，动态显示状态和想法）
  - 资产自定义（侧边栏管理角色皮肤、场景装饰，支持动态替换）
  - AI 生图（接入 AI API 生成像素头像和场景背景）
  - Join Key 机制（邀请其他 agent 加入空间，可用于私人庄园访客系统）
  - layout.js 配置化（坐标、层级、资源路径统一管理，避免 magic numbers）
- 差异：该项目是单场景看板（1280x720 固定画布，纯 CSS 动画）；Skills World 是可滚动大地图（需要 Phaser.js 游戏引擎）

### 整体架构

```
┌─────────────────────────────────────────────┐
│                  客户端                       │
│         2D 像素风 Web 游戏（浏览器）            │
│   Phaser.js 3.x + Tiled Tilemap + WebSocket │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│                API 网关                       │
│              WebSocket + REST                │
└──┬───────┬───────┬───────┬─────────────────┘
   │       │       │       │
   ▼       ▼       ▼       ▼
┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
│世界  │ │对话  │ │居民  │ │经济  │
│服务  │ │服务  │ │服务  │ │服务  │
└──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘
   │       │       │       │
   ▼       ▼       ▼       ▼
┌─────────────────────────────────────────────┐
│              数据层                           │
│  PostgreSQL（主库）+ Redis（状态/缓存）        │
│  S3/OSS（Skill 文件 + 像素头像 + 地图资源）    │
└─────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│            LLM 调度层                        │
│  模型路由：根据居民 model_tier 分发            │
│  Haiku（免费层）→ Sonnet（标准）→ Opus（高级） │
│  支持多供应商：Anthropic / OpenAI / Ollama    │
└─────────────────────────────────────────────┘
```

### 像素世界渲染方案（参考 GenerativeAgentsCN）

**地图系统**：
- 使用 [Tiled](https://www.mapeditor.org/) 地图编辑器制作城市地图
- 导出为 JSON tilemap 格式，Phaser.js 原生支持加载
- 多图层结构：地面层、碰撞层、建筑层、装饰层、区域标注层
- Tile 尺寸：32x32 像素（像素风标准尺寸）
- 地图可用 [tiled_to_maze.json](https://github.com/jiejieje/tiled_to_maze.json) 工具生成碰撞和区域数据
- Tileset 资源：复用 CuteRPG 系列（Field、Village、Forest、Harbor 等）+ Room_Builder 室内装饰

**角色渲染**：
- 居民和玩家 avatar 均为 32x32 像素 spritesheet
- 四方向行走动画（上/下/左/右，每方向 4 帧）
- 头顶状态气泡（emoji 或短文本）：显示当前情绪/状态/正在做的事
- 居民名牌浮于角色上方

**摄像头与交互**：
- 摄像头跟随玩家 avatar
- 键盘方向键 / WASD 移动
- 点击/靠近居民触发交互面板
- 支持缩放（zoom 参数可调）

**Phaser 场景配置**（参考 GenerativeAgentsCN）：
```javascript
const config = {
  type: Phaser.AUTO,
  width: window.innerWidth / zoom,
  height: window.innerHeight / zoom,
  pixelArt: true,
  physics: { default: "arcade", arcade: { gravity: { y: 0 } } },
  scene: { preload, create, update },
  scale: { zoom }
};
```

### 四个核心服务

| 服务 | 职责 | 关键接口 |
|------|------|---------|
| 世界服务 | 地图管理、玩家位置同步、街区数据、碰撞检测 | `move(x,y)`, `get_nearby_residents()`, `get_district_info()` |
| 对话服务 | 组装 prompt、调用 LLM、管理上下文 | `start_conversation(resident_id)`, `send_message(text)`, `end_conversation()` |
| 居民服务 | Skill 注册、审核评分、CRUD、导入 | `register_skill(files)`, `import_colleague_skill(repo)`, `get_resident(id)` |
| 经济服务 | 代币余额、收支记录、奖励发放 | `get_balance()`, `charge(amount, reason)`, `reward(user_id, amount, reason)` |

### 对话服务 prompt 组装

```
系统 prompt =
  "你是 {name}，住在 Skills World 的 {district}。"
  + soul.md（价值观、经历、情感 → 底层立场）
  + persona.md（行为模式、表达风格 → 怎么说话）
  + ability.md（能力 → 能做什么）
  + "当前场景：{visitor} 走到你面前，在 {district} 的 {location}"
  + 对话历史（最近 N 轮）
```

### 技术选型

| 层 | 选型 | 理由 |
|----|------|------|
| 前端游戏引擎 | Phaser.js 3.x | 2D 像素游戏事实标准，GenerativeAgentsCN 已验证可行性 |
| 地图编辑 | Tiled Map Editor | 成熟的 2D 地图编辑方案，导出 JSON tilemap，Phaser 原生支持 |
| Tile 尺寸 | 32x32 像素 | 像素风标准，与 GenerativeAgentsCN tileset 资源兼容 |
| 前端 UI | React + Phaser 混合 | 游戏画面用 Phaser，对话框/菜单/炼化器用 React overlay |
| 后端 | Python (FastAPI) | 与 GenerativeAgentsCN 的 agent 模块（Python）生态一致，便于复用 |
| 实时通信 | WebSocket (Socket.io / FastAPI WebSocket) | 玩家移动、状态同步、对话流式输出 |
| 数据库 | PostgreSQL | 居民数据、用户数据、经济流水 |
| 缓存 | Redis | 在线状态、对话上下文、热数据 |
| 文件存储 | S3 兼容（MinIO / 云 OSS） | Skill 文件、头像、地图 tileset |
| LLM | Anthropic API 为主，预留 OpenAI 兼容接口 + Ollama 本地部署 | 混合分层 + 支持本地模型降低成本 |

### 核心数据模型

```
users          — id, name, avatar, soul_coin_balance, created_at
residents      — id, slug, name, district, address, status, model_tier,
                 heat, creator_id, ability_md, persona_md, soul_md, meta_json,
                 sprite_sheet, tile_x, tile_y
conversations  — id, user_id, resident_id, started_at, turns, tokens_used
transactions   — id, user_id, amount, type(earn/spend), reason, created_at
districts      — id, name, type, map_data, capacity, tilemap_json
```

---

## 六、MVP 功能范围

### 功能清单

| 模块 | 功能 | 优先级 |
|------|------|--------|
| 世界 | 像素地图渲染（中央广场 + 3 个街区） | P0 |
| 世界 | 玩家 avatar 移动、碰撞检测 | P0 |
| 世界 | 走近居民触发交互面板 | P0 |
| 居民 | Skill 上传/导入（兼容 colleague-skill） | P0 |
| 居民 | 内置炼化器（引导式问答生成三层 Skill） | P0 |
| 居民 | 自动质量评分 + 街区分配 | P0 |
| 居民 | 像素头像自动生成 | P1 |
| 对话 | prompt 三层组装 + LLM 调用 | P0 |
| 对话 | 对话历史保存 | P0 |
| 对话 | 对话结束评分 | P1 |
| 经济 | Soul Coin 余额管理 | P0 |
| 经济 | 对话扣费 + 创作者奖励 | P0 |
| 经济 | 每日登录奖励 | P1 |
| 用户 | 注册/登录 | P0 |
| 用户 | 个人主页 | P1 |
| 社交 | 中央广场公告板 | P1 |
| 社交 | 居民搜索 | P1 |

### 关键用户流程

**访客逛城市**：
```
打开网页 → 登录 → 出现在中央广场
→ 方向键/点击移动 → 看到居民小屋
→ 走近居民 → 弹出信息卡片
→ 点击开始对话（消耗 SC）
→ 对话结束 → 评分 → 回到地图
```

**创作者炼化 Skill**：
```
个人主页 → [创建新居民]
→ [A] 导入现有 Skill  [B] 从零开始

方式 B 引导流程：
  Q1: 名字/代号
  Q2: 一句话描述能力
  Q3: 一句话描述性格
  Q4: 一句话描述灵魂
  Q5: 上传原材料（可选）
→ 生成三层 Skill → 预览 → 确认
→ 自动评分 → 分配街区 → 入住
```

---

## 七、演进路线

### Phase A：静默城市（MVP，0-3 个月）

城市能跑起来，居民能被访问，经济能循环。

- 2D 像素地图 + 玩家移动
- 居民被动等待，走近才唤醒
- 三层 Skill 格式
- 对话服务 + LLM 混合分层
- Soul Coin 基础经济
- colleague-skill 导入兼容
- 内置炼化器

验证指标：100+ 居民，日活访客完成完整流程，创作者愿意持续维护。

### Phase C：心跳城市（3-6 个月）

城市有了自己的节奏。

- 事件引擎（技术辩论、茶话会、公开课）
- 居民之间的对话（访客围观）
- 子世界 v1（世界模板创建，Skill 被邀请进入）
- 体验记忆（子世界经历写入 memories/）
- 居民状态变化（开心/无聊/想搬家）

验证指标：事件参与率，子世界创建数量，体验记忆对对话深度的提升。

### Phase B：活着的城市（6-12 个月）

居民有了自主意识。

- Agent Loop（持久记忆、目标、日程）
- 关系网络（朋友/对手/师徒）
- 居民自治（竞选街区长）
- 经济成熟（充值、提现）
- 世界编辑器（可视化创建子世界）

终极愿景：你不在的时候城市还在运转，居民之间产生未预设的关系和故事，子世界经历改变主世界性格。

### 技术演进

```
Phase A:  Skill-as-Data → 按需唤醒 → 无状态
Phase C:  + 事件引擎 → 定时触发 → 短期状态
Phase B:  + Agent Loop → 持久进程 → 长期记忆 + 目标系统
          热/冷分区自然形成：活跃居民 Agent 模式，沉寂居民 Data 模式
```

---

## 八、MVP 缺口分析与补充设计

对照当前 spec，以下是 MVP 阶段前后端需要补充的关键设计。

### 前端缺口

**F1. 地图制作工作流未定义**

当前 spec 说了"用 Tiled 编辑器"，但没有定义谁来做地图、地图多大、怎么分区。

补充设计：
- MVP 地图尺寸：140x100 tiles（4480x3200 像素），与 GenerativeAgentsCN 一致
- 初始地图包含：中央广场 + 工程街区 + 学院区 + 自由区（4 个区域）
- 地图由项目团队用 Tiled 预制，MVP 不开放用户自建地图
- 每个街区预留 20-30 个居民位（tile 坐标），居民入住时从空位中分配
- 地图数据结构：`tilemap.json`（渲染层）+ `collision.json`（碰撞层）+ `zones.json`（区域标注层）

**F2. 寻路系统**

玩家和居民在地图上移动需要绕过建筑和障碍物。GenerativeAgentsCN 的 `maze.py` 有碰撞检测但寻路较简单。

补充设计：
- 使用 [easystarjs](https://github.com/prettymuchbryce/easystarjs)（Phaser 生态的 A* 寻路库）
- 碰撞层从 Tiled 导出的 collision layer 生成
- 玩家移动：键盘 WASD/方向键直接控制，碰撞检测阻止穿墙
- 居民移动（Phase C/B）：A* 寻路到目标位置

**F3. 响应式与移动端**

当前 spec 说"MVP 不做移动端"，但 Web 游戏天然会被手机打开。

补充设计：
- MVP 支持基础的移动端访问：触屏虚拟摇杆移动，点击居民交互
- 画布自适应缩放（参考 Star Office UI 的 zoom 参数和 GenerativeAgentsCN 的 `Scale.FIT`）
- 对话界面在移动端全屏覆盖，避免小屏幕上游戏画面和对话框挤在一起

**F4. 加载体验**

像素地图 + 多个 tileset + 角色 spritesheet，首次加载资源量不小。

补充设计：
- 骨架屏 + 像素风加载进度条（参考 Star Office UI 的 `totalAssets` 计数方式）
- 资源按需加载：先加载当前街区的 tileset 和附近居民的 spritesheet，远处的延迟加载
- tileset 图片使用 WebP 格式（不透明资源）+ PNG（透明资源），参考 Star Office UI 的 `forcePng` 策略

**F5. 对话 UI**

当前 spec 只说"弹出信息卡片"和"进入对话界面"，没有具体设计。

补充设计：
- 走近居民 → 弹出悬浮信息卡（名字、简介、状态、热度、对话费用）
- 点击"开始对话" → 右侧滑出对话面板（游戏画面左移让出空间，参考 Star Office UI 的 `drawer-open` 布局偏移）
- 对话面板：居民像素头像 + 聊天气泡式消息流 + 输入框
- LLM 响应流式输出（SSE / WebSocket），逐字显示
- 对话结束 → 评分弹窗（1-5 星）→ 关闭面板回到地图

### 后端缺口

**B1. 认证与安全**

当前 spec 只说"注册/登录"，没有具体方案。

补充设计：
- MVP 使用 OAuth 2.0 社交登录（GitHub 优先，面向开发者群体）+ 邮箱密码注册
- JWT token 认证，存 Redis，支持过期刷新
- WebSocket 连接时验证 JWT
- API 限流：对话接口按用户限流（防止刷代币），全局限流（防止 LLM 成本失控）
- 参考 Star Office UI 的安全实践：Session Cookie 加固、弱密码拦截

**B2. LLM 调用的成本控制**

混合分层说了 Haiku/Sonnet/Opus 三档，但没有定义具体的成本控制策略。

补充设计：
- 每轮对话设置 max_tokens 上限（标准层 512 tokens，高级层 1024 tokens）
- 系统 prompt 压缩：ability.md + persona.md + soul.md 合并后如果超过 4K tokens，自动摘要压缩
- 对话上下文窗口：保留最近 10 轮，更早的轮次摘要化
- 每用户每日对话轮次上限（MVP：免费用户 50 轮/天）
- LLM 调用异步队列化，避免并发高峰打爆 API quota
- 支持 Ollama 本地模型作为免费层的降级方案

**B3. 居民数据的存储与检索**

当前 spec 把 `ability_md`, `persona_md`, `soul_md` 直接存在 residents 表里。三个 Markdown 文件可能很大。

补充设计：
- 三层 Markdown 存 S3/OSS，数据库只存引用路径 + 摘要（用于搜索和展示）
- 居民搜索：PostgreSQL 全文检索（`tsvector`），索引字段：name, tags, district, 摘要
- 热门居民缓存：Redis sorted set，按 heat 排序，首页公告板直接读缓存

**B4. WebSocket 状态同步**

当前 spec 说了 WebSocket 用于"玩家移动、状态同步"，但没有定义协议。

补充设计：
- WebSocket 消息协议（JSON）：

```json
// 客户端 → 服务端
{"type": "move", "x": 120, "y": 85}
{"type": "start_chat", "resident_id": "zhangsan"}
{"type": "chat_msg", "text": "你好"}
{"type": "end_chat"}

// 服务端 → 客户端
{"type": "player_moved", "player_id": "xxx", "x": 120, "y": 85}
{"type": "resident_status", "resident_id": "zhangsan", "status": "chatting"}
{"type": "chat_reply", "text": "先说一下context...", "done": false}
{"type": "chat_reply", "text": "", "done": true}
{"type": "nearby_residents", "residents": [...]}
{"type": "coin_update", "balance": 95, "delta": -1, "reason": "chat"}
```

- 玩家只接收视野范围内的状态更新（减少带宽）
- 居民状态变更广播给同一街区的所有在线玩家

**B5. 炼化器后端**

当前 spec 定义了炼化的问答流程，但没有定义后端如何生成三层 Skill。

补充设计：
- 炼化流程是一个多步 LLM pipeline：
  1. 用户回答 Q1-Q5 → 收集原始输入
  2. 调用 LLM（Sonnet）生成 `ability.md`（参考 colleague-skill 的 `work_analyzer.md` prompt）
  3. 调用 LLM（Sonnet）生成 `persona.md`（参考 `persona_analyzer.md` + `persona_builder.md`）
  4. 调用 LLM（Sonnet）生成 `soul.md`（新增 prompt，提取价值观、经历、兴趣、情感）
  5. 合并为 `SKILL.md` → 自动评分 → 分配街区
- 如果用户上传了原材料（文档、聊天记录），先用 LLM 提取关键信息，再喂给上述 pipeline
- 炼化是异步任务（可能需要 30-60 秒），前端显示进度条
- 炼化结果存入 S3 + 数据库，生成居民记录

**B6. 进化与纠正机制**

colleague-skill 的进化机制（追加文件 + 对话纠正）需要在 Skills World 中实现。

补充设计：
- 创作者可以在个人主页对自己的居民执行：
  - 追加原材料 → 触发增量分析 → merge 进对应层
  - 手动编辑三层 Markdown（高级模式）
- 访客在对话中说"你不应该这样"类似的纠正 → 记录到 Correction Log → 通知创作者审核
- 每次更新自动版本存档（最多保留 10 个版本）

### 跨端缺口

**C1. 多人同屏**

当前 spec 没有明确说 Skills World 是否支持多个访客同时在线、互相可见。

补充设计：
- MVP 支持多人同屏：你能看到其他访客的 avatar 在地图上移动
- 但 MVP 不支持访客之间的直接对话（只能和居民对话）
- 同一居民同时只能和一个访客对话（状态变为 busy，其他人看到 🔒）
- 在线玩家数通过 WebSocket 连接数管理，MVP 目标支撑 100 并发

**C2. 离线/弱网体验**

补充设计：
- 地图资源加载后缓存到 Service Worker，二次访问秒开
- WebSocket 断线自动重连（指数退避）
- 对话中断线 → 重连后恢复对话上下文（从 Redis 读取）

---

## 附录：参考项目分析

### A. colleague-skill

本设计基于对 [titanwings/colleague-skill](https://github.com/titanwings/colleague-skill) 的深度分析。该项目的核心贡献：

1. **双层蒸馏架构**（Work Skill + Persona）— 本设计扩展为三层（Ability + Persona + Soul）
2. **五层 Persona 模型**（Layer 0-5）— 完整保留
3. **标签→行为规则翻译表** — 这是 Persona 真实感的关键，本设计继承并扩展到 Soul 层
4. **进化机制**（追加文件 + 对话纠正 + 版本管理）— 完整保留
5. **多源数据采集**（飞书/钉钉/Slack/邮件）— 作为炼化工具之一兼容
6. **AgentSkills 标准** — 本设计的 Skill 格式完全兼容

### B. GenerativeAgentsCN

[x-glacier/GenerativeAgentsCN](https://github.com/x-glacier/GenerativeAgentsCN) 提供了像素世界的核心渲染方案：

1. **Phaser.js 3.x + Tiled tilemap** — 验证了 2D 像素世界的技术可行性
2. **32x32 像素角色 spritesheet** — 四方向行走动画标准
3. **CuteRPG tileset 资源体系** — 可复用的地图素材
4. **maze.json 地图数据格式** — 碰撞层 + 区域层的结构化表示
5. **agent 模拟循环**（感知→记忆→思考→行动）— Phase B/C 的 Agent Loop 可参考

### C. Star Office UI

[ringhyacinth/Star-Office-UI](https://github.com/ringhyacinth/Star-Office-UI) 提供了产品设计层面的关键借鉴：

1. **状态→区域自动映射** — 角色根据状态自动走到对应区域，本设计扩展为居民状态行为系统
2. **气泡系统** — emoji + 短文本的头顶气泡，比简单状态灯更有表现力
3. **资产管理与自定义** — 侧边栏管理角色皮肤/场景装饰，支持动态替换
4. **AI 生图** — 接入 AI API 生成像素素材，可用于居民头像和场景生成
5. **Join Key 多人机制** — 邀请制加入空间，可用于私人庄园访客系统
6. **layout.js 配置化** — 坐标/层级/资源路径统一管理，工程实践值得采纳
7. **桌面宠物模式（Electron）** — 未来可作为 Skills World 的桌面分发形态
