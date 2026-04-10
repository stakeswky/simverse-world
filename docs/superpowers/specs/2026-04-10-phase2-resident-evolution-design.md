# Phase 2 设计：居民进化 — 记忆、多模态、自主行为、人格演化

## 概述

Phase 2 让虚拟居民从"被动应答者"进化为"自主生命体"。四个子系统协同工作：三层记忆赋予居民独立的经历积累，多模态输入让居民能理解图片和视频，自主行为循环让居民有自己的作息和社交生活，人格演化让居民的性格随时间和经历真实地成长。

**架构选型：方案 A — 集中式 AgentLoop**
- 统一的后台服务驱动所有居民行为
- 与现有 FastAPI + async + WebSocket 架构契合
- 集中调度便于 LLM 成本控制
- 当前居民规模（20-50）下 async 协程足够，未来可演进为多 worker

## 交付顺序

| 顺序 | 子项目 | 依赖 | 说明 |
|------|--------|------|------|
| P1 | 记忆系统 | 无 | 基础设施，其他子系统都依赖它 |
| P2 | 多模态输入 | P1 | 图片/视频需要存入记忆 |
| P3 | 自主行为循环 + 居民间沟通 | P1 | 需要记忆驱动决策 |
| P4 | 人格动态演化 | P1 + P3 | 需要记忆积累和社交数据 |

每个子项目独立走 spec → plan → implement 周期。

---

## P1：三层记忆系统

### 数据模型

三层记忆共用一张 `memories` 表 + pgvector 扩展：

```sql
memories
  id              SERIAL PRIMARY KEY
  resident_id     INT FK → residents
  type            ENUM("event", "relationship", "reflection")
  content         TEXT              -- 自然语言描述
  embedding       VECTOR(1024)      -- 仅 event 类型必填，Ollama qwen3-embedding:4b (MRL 降维到 1024)
  importance      FLOAT             -- 0-1, LLM 评估
  related_resident_id  INT?         -- 关系记忆指向的居民
  related_user_id      INT?         -- 与玩家的关系记忆
  source          ENUM("chat_player", "chat_resident", "observation", "reflection", "media")
  media_url       TEXT?             -- 关联的图片/视频路径
  media_summary   TEXT?             -- 多模态模型生成的描述
  metadata_json   JSON              -- 话题标签、情绪、地点等
  created_at      TIMESTAMP
  last_accessed_at TIMESTAMP        -- 用于时间衰减
```

### 三层记忆生命周期

**事件记忆（Event）** — 每次交互后自动生成：
- 玩家聊天结束 → 提取 1-3 条关键事件记忆
- 居民间对话结束 → 双方各自生成事件记忆
- 看到图片/视频 → 生成一条带 media_summary 的事件记忆
- 生成 embedding 用于语义检索

**关系记忆（Relationship）** — 每个认识的人维护一条，持续更新：
- 首次接触时创建（如 `"初次见面，对方是工程区的程序员，聊了AI话题"`）
- 后续交互时 LLM 基于旧关系记忆 + 新事件记忆重写 content
- metadata_json 中存储：好感度趋势、信任度、关键印象标签

**反思记忆（Reflection）** — 定期由 AgentLoop 触发：
- 触发条件：积累 10-20 条新事件记忆，或距上次反思超过一定游戏时间
- 过程：取最近事件记忆 + 关系记忆 → LLM 提炼 2-3 条高层认知
- 示例：`"工程区的人似乎都很忙，很少主动找我聊天"` / `"小明每次都问我技术问题，从不关心我的感受"`

### 检索策略

聊天时组装上下文的检索流程：

1. **结构化查询：** 该对话对象的关系记忆（1条，O(1)）
2. **结构化查询：** 最近的反思记忆（top 3-5，按 importance 排序）
3. **向量检索：** 与当前话题语义相关的事件记忆（top 5-10，pgvector cosine similarity）
4. **时间衰减加权：** 按 relevance × recency 排序，取 top K 条注入 system prompt

### SBTI 对记忆的影响

不同人格维度影响居民"记住什么"和"怎么解读"：

| 维度 | 对记忆的影响 |
|------|------------|
| E1 依恋安全感 (高) | 更容易记住关系性事件，关系记忆中好感度变化更敏感 |
| E2 情感投入度 (高) | 事件记忆的 importance 评分偏高，更"走心" |
| S2 自我清晰度 (高) | 反思记忆更聚焦、更有条理，较少模糊泛化 |
| A1 世界观倾向 (低) | 反思时倾向悲观解读 |
| So3 表达真实度 (低) | 关系记忆中可能隐藏真实感受 |

实现方式：生成记忆时将居民的 SBTI 维度注入 LLM prompt，引导记忆的"着色"方向。不是硬编码规则，而是 prompt 层面的性格调制。

### 技术选型

- **pgvector**：PostgreSQL 扩展，不需要额外基础设施。SQLite 开发时退化为关键词匹配
- **Embedding 模型**：本地部署 Ollama qwen3-embedding:4b（2.5GB），通过 MRL 降维到 1024 维。本地部署零边际成本，适合高频记忆生成场景。Ollama API: `POST http://localhost:11434/api/embed`
- **记忆上限**：每个居民事件记忆 soft cap 500 条，超出后按 importance × recency 淘汰最旧的

---

## P2：多模态输入

### 场景 A：玩家发送图片/视频给居民

```
玩家在聊天中上传图片/视频
  → 前端上传到 POST /api/media/upload → 返回 media_url
  → WebSocket 发送 ChatMsg(text, media_url?, media_type?)
  → 后端根据 media_type 路由模型：
      - image → qwen3.6-plus（主模型，直接传图）
      - video → 临时切换 kimi-k2.5，获取视频理解结果，再切回主模型继续对话
  → 居民"看懂"内容并回应
  → 自动生成事件记忆（content + media_url + media_summary）
```

### 场景 B：居民间共享视觉信息

```
居民 A 与玩家聊天中看到图片 → 事件记忆保存 media_url + media_summary
  → 居民 A 与居民 B 自主对话时，话题相关 → 检索到带图记忆
  → 居民 A 通过 media_summary（文本）向 B "描述"图片内容
  → 居民 B 生成自己的事件记忆（source="chat_resident"）
```

居民间传递的是文本摘要而非原图——类似真人转述"我看到了一张XX的照片"。避免额外多模态调用。

### 模型路由

```python
class ModelRouter:
    PRIMARY = "qwen3.6-plus"      # 默认，支持图片
    VIDEO   = "kimi-k2.5"         # 视频理解专用

    async def chat_with_media(self, messages, media_url, media_type):
        if media_type == "video":
            summary = await self._video_understand(media_url)
            messages.append({"role": "user", "content": f"[视频内容：{summary}]"})
            return await self._chat(self.PRIMARY, messages)
        elif media_type == "image":
            return await self._chat(self.PRIMARY, messages, image_url=media_url)
        else:
            return await self._chat(self.PRIMARY, messages)
```

### 媒体存储

```
backend/static/uploads/
  ├── images/{uuid}.{ext}    # 压缩后存储，上限 5MB
  └── videos/{uuid}.{ext}    # 原始存储，上限 50MB

清理策略：30 天未被任何记忆引用的媒体文件自动清理
```

### API 变更

```
POST /api/media/upload
  - multipart/form-data: file + media_type
  - 返回 { media_url, media_type }
  - 鉴权：需登录，限速 10 次/分钟

WebSocket ChatMsg 扩展：
  现有：{ type: "chat_msg", text: "..." }
  新增：{ type: "chat_msg", text: "...", media_url?: "...", media_type?: "image|video" }
```

### 前端变更

ChatDrawer 新增：
- 附件上传按钮（聊天输入框旁），支持图片和视频
- 消息气泡中渲染图片缩略图 / 视频预览
- 上传进度条

---

## P3：居民自主行为循环 + 居民间沟通

### AgentLoop 架构

```
FastAPI startup
  └── asyncio.create_task(AgentLoop.run())

AgentLoop.run():
  while True:
    1. 计算当前"世界时间"
    2. 遍历所有居民，根据作息表决定谁该"醒来思考"
    3. 对每个活跃居民，并发执行 resident_tick()
    4. sleep(TICK_INTERVAL)  # 基础间隔 60 秒
```

### 时间系统与作息

世界时钟与现实时间同步（1:1），可配置倍速用于测试。

作息参数由 SBTI 维度推导：

```python
class DailySchedule:
    wake_hour: int       # 起床时间 (Ac1 高→早起)
    sleep_hour: int      # 睡觉时间
    peak_hours: list     # 高活跃时段 (So1 高→白天多段活跃)
    social_slots: int    # 每天主动社交次数上限 (So1 + E2 决定)
    rest_ratio: float    # 休息占比 (E3 高→更多独处时间)
```

活跃度是概率曲线而非开/关二值。每次 tick 居民按当前时段的活跃概率决定是否执行 `resident_tick()`，加随机抖动避免同步行动。

### 行为谱

```
行为类型            描述                                SBTI 倾向性
───────────────────────────────────────────────────────────────
社交类
  CHAT_RESIDENT     主动找另一个居民聊天                  So1↑ E2↑
  CHAT_FOLLOW_UP    对之前未聊完的话题找人继续聊            E1↑ Ac3↑
  GOSSIP            找人分享从别处听来的事（传播记忆）       So1↑ So3↓

移动类
  WANDER            在所属街区内闲逛                      Ac1↓ (无目标时)
  VISIT_DISTRICT    去其他街区逛逛                        A1↑ So1↑
  GO_HOME           回到自己的常驻位置                     E3↑ (需要独处)

观察类
  OBSERVE           观察周围的人和事，生成观察记忆          S2↑ A3↑
  EAVESDROP         旁听附近居民的对话（获取摘要）          So3↓ S2↑

自省类
  REFLECT           整理最近记忆，产出反思                  S2↑ A3↑
  JOURNAL           写"内心日记"（内心独白式记忆）          S3↑ E2↑

创作/工作类
  WORK              做与 ability_md 相关的事               Ac1↑ Ac3↑
  STUDY             基于最近对话或观察学习新东西             A3↑ Ac1↑

休息类
  IDLE              发呆、放空                             默认行为
  NAP               短暂休息（降低活跃度）                  E3↑
```

### 行为与移动绑定

居民不会瞬移——每个行为关联移动模式：

| 行为 | 移动模式 |
|------|---------|
| CHAT_RESIDENT / GOSSIP | 寻路到目标居民位置 → 面对面 |
| VISIT_DISTRICT | 寻路到目标街区的随机位置 |
| GO_HOME | 寻路回常驻 tile |
| WANDER | 随机选附近 3-5 tile，漫步过去 |
| OBSERVE | 移动到视野好的位置，或原地不动 |
| EAVESDROP | 移动到聊天居民附近（保持 2-3 tile 距离）|
| WORK/STUDY | 移动到所属街区功能区域 |
| REFLECT/JOURNAL/IDLE/NAP | 原地不动或移动到安静角落 |

寻路使用 A* 算法，基于 tilemap 碰撞层。移动速度受 Ac3 维度影响（基础 1 tile/2s，Ac3=H → 1 tile/1.5s）。

### resident_tick() — 思考周期

```
resident_tick(resident):
  1. Perceive（感知）
     - 查询最近事件（新对话、被提及、收到图片）
     - 查询附近居民（tile 距离 < N）
     - 查询未处理的关系变化

  2. Retrieve（检索记忆）
     - 最近反思记忆 top 3
     - 与附近居民的关系记忆
     - 语义检索相关事件记忆

  3. Decide（LLM 决策）
     输入：感知 + 记忆 + SBTI 维度 + 当前状态
     输出：{ action, target?, reason }
     可选行动：IDLE/MOVE/CHAT/OBSERVE/REFLECT/SLEEP/WORK/GOSSIP/...

  4. Execute（执行）
     - 移动到目标位置（如需要）
     - 执行行为
     - 广播状态变更

  5. Memorize（记忆沉淀）
     - 本次行动生成事件记忆
     - 检查是否触发关系记忆更新
     - 检查是否触发反思
```

### LLM 决策 prompt 结构

```
你是 {name}，SBTI 类型 {type}({type_name})。

你的性格维度：{15维解读}

当前状态：
- 时间：{世界时间}，你的作息处于 {peak/normal/low} 时段
- 位置：{district} 街区 ({tile_x}, {tile_y})
- 附近的人：{nearby_residents with relationship summaries}
- 最近发生的事：{recent_event_memories top 3}
- 你最近的想法：{recent_reflections top 2}
- 你今天已经做了：{today_actions_summary}

可选行动：{available_actions with descriptions}

基于你的性格和当前情况，你现在想做什么？为什么？
输出格式：{ "action": "...", "target": "...", "reason": "..." }
```

### 居民间对话流程

```
居民 A 决定与居民 B 聊天：
  1. 检查 B 的状态（sleeping/chatting → 放弃或等待）
  2. 锁定双方状态为 socializing
  3. 组装双方 system prompt（三层人格 + SBTI + 关系记忆）
  4. 对话 3-8 轮（轮次由话题深度和 Ac3 决定）：
     - A → LLM(A 的人格 + 记忆) 生成
     - B → LLM(B 的人格 + 记忆) 生成
     - 每轮检查自然结束（[END] 标记）
  5. 对话结束：
     - 双方各自生成事件记忆
     - 更新关系记忆
     - 生成话题摘要
  6. 广播：{ type: "resident_chat", residents: [A, B], summary: "..." }
  7. 解锁双方状态
```

### 前端表现

居民状态扩展：
- 现有：idle / chatting / sleeping / busy
- 新增：walking（移动中）/ socializing（与居民聊天）

视觉表现：
- `walking` → sprite 沿路径平滑移动，播放行走动画
- `socializing` → 两居民面对面，头上显示对话气泡
- 点击 socializing 居民 → 浮窗显示话题摘要

WebSocket 新消息类型：

```
server → client:
  resident_move:     { slug, path: [{x,y}, ...] }
  resident_chat:     { slugs: [a, b], summary, started_at }
  resident_chat_end: { slugs: [a, b] }
  resident_status:   { slug, status }
```

### 资源控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| TICK_INTERVAL | 60s | 基础 tick 间隔 |
| MAX_CONCURRENT_TICKS | 5 | 同时执行的居民思考数 |
| MAX_DAILY_ACTIONS | 20/居民 | 每日非 IDLE 行动上限 |
| CHAT_MAX_TURNS | 8 | 居民间对话最大轮次 |
| CHAT_COOLDOWN | 30min | 同一对居民的对话冷却 |
| LLM_RATE_LIMIT | 30/min | 全局 LLM 调用限速 |

所有参数通过 SystemConfig 表可在 Admin 面板动态调整。

---

## P4：人格动态演化

### 渐变（Drift）

日常交互的缓慢积累。

- **触发条件：** 每积累 15-20 条新事件记忆
- **流程：** 收集近期记忆 → 对比当前 SBTI 15 维 → LLM 评估变化依据 → 调整 1-2 个维度（±1） → 重新 match_type()
- **约束：** 每次最多改 2 维，步长 ±1（L↔M↔H，不允许 L→H 跳跃）

**示例：** So1=L 的居民被多人主动搭话且聊得不错 → So1: L→M → 开始偶尔主动找人聊天。

### 跳变（Shift）

关键事件触发的显著人格转变。

- **触发条件：** 事件记忆 importance ≥ 0.9
- **关键事件类型：**
  - 深度共鸣：对话触及 soul_md 核心价值
  - 信任破裂：隐私被传播（GOSSIP 链追溯）
  - 认知冲突：反思发现行为与价值观矛盾
  - 群体排斥/接纳：被多人同时冷落或欢迎
- **流程：** 标记 trigger_shift → 立即触发特殊反思 → LLM 评估冲击 → 调整 2-3 个维度（±2，允许 L→H） → 重新 match_type() → 生成"为什么我变了"的反思记忆
- **约束：** 跳变冷却 24 小时，防连续剧变

**示例：** MONK（E1=L）深度对话后产生强烈共鸣 → E1: L→M, E2: L→M → 可能迁移为 THIN-K → 反思："原来与人连接并不意味着软弱"

### 演化约束

```python
class PersonalityGuard:
    MAX_DRIFT_PER_CYCLE = 2        # 渐变每次最多改 2 个维度
    MAX_SHIFT_PER_EVENT = 3        # 跳变每次最多改 3 个维度
    DRIFT_STEP = 1                 # 渐变步长 ±1
    SHIFT_STEP = 2                 # 跳变步长 ±2
    MIN_DRIFT_INTERVAL = 15        # 两次渐变之间至少 15 条新记忆
    SHIFT_COOLDOWN = 24h           # 跳变冷却 24 小时
    TOTAL_MONTHLY_CHANGE = 8       # 每月所有维度变化总量上限
```

### 三层文本同步

SBTI 维度变化后，三层文本需要相应调整：

- **persona_md：** 渐变和跳变时，LLM 重写受影响维度相关的段落，保留核心框架
- **soul_md：** 仅跳变时审视是否需要补充新价值观
- **ability_md：** 不变（能力不因性格改变）

实现方式：LLM diff — 输入旧文本 + 变化说明，输出修改后文本。

### 演化历史表

```sql
personality_history
  id              SERIAL PRIMARY KEY
  resident_id     INT FK → residents
  trigger_type    ENUM("drift", "shift")
  trigger_memory_id  INT? FK → memories
  changes_json    JSON    -- { "So1": {"from": "L", "to": "M"}, ... }
  old_type        TEXT    -- 旧 SBTI 类型
  new_type        TEXT    -- 新 SBTI 类型（可能相同）
  reason          TEXT    -- LLM 生成的变化原因
  created_at      TIMESTAMP
```

### 前端表现

- 类型迁移时前端收到 `resident_type_changed` 事件
- SBTI 标签闪烁动画 + 旧→新类型渐变
- 居民详情页可查看演化历史时间线（后续版本）

---

## 数据库变更汇总

### 新建表

| 表 | 用途 |
|----|------|
| `memories` | 三层记忆（event/relationship/reflection），含 pgvector embedding |
| `personality_history` | 人格演化历史记录 |

### 修改表

| 表 | 变更 |
|----|------|
| `residents` | 新增 `home_tile_x/y`（常驻位置），status 枚举新增 walking/socializing |

### 新增扩展

| 扩展 | 用途 |
|------|------|
| pgvector | PostgreSQL 向量检索（事件记忆 embedding） |

---

## 新增文件清单

### 后端

```
backend/app/
  ├── agent/
  │   ├── __init__.py
  │   ├── loop.py              # AgentLoop 主循环
  │   ├── tick.py              # resident_tick() 感知-决策-执行
  │   ├── scheduler.py         # 作息调度，SBTI→DailySchedule
  │   ├── actions.py           # 行为定义和执行逻辑
  │   ├── pathfinder.py        # A* 寻路
  │   └── prompts.py           # 决策/记忆/反思 prompt 模板
  ├── memory/
  │   ├── __init__.py
  │   ├── service.py           # 记忆 CRUD + 检索
  │   ├── embedding.py         # embedding 生成（本地 Ollama qwen3-embedding:4b, 1024维）
  │   └── reflection.py        # 反思生成逻辑
  ├── personality/
  │   ├── __init__.py
  │   ├── evolution.py         # 渐变/跳变逻辑
  │   └── guard.py             # PersonalityGuard 约束
  ├── media/
  │   ├── __init__.py
  │   ├── service.py           # 媒体上传/存储/清理
  │   └── router.py            # ModelRouter 多模态路由
  ├── models/
  │   ├── memory.py            # Memory ORM 模型
  │   └── personality_history.py  # PersonalityHistory ORM 模型
  └── routers/
      └── media.py             # POST /api/media/upload
```

### 前端

```
frontend/src/
  ├── components/
  │   ├── chat/
  │   │   └── MediaUpload.tsx  # 图片/视频上传组件
  │   └── game/
  │       └── ResidentBubble.tsx  # 居民对话气泡/摘要浮窗
  └── game/
      └── PathAnimation.ts     # 居民移动补间动画
```

### 修改文件

```
backend/app/
  ├── main.py                  # 启动时创建 AgentLoop task
  ├── llm/client.py            # 集成 ModelRouter
  ├── llm/prompt.py            # system prompt 注入记忆上下文
  ├── ws/handler.py            # ChatMsg 支持 media_url/media_type
  ├── ws/protocol.py           # 新消息类型定义
  ├── ws/manager.py            # 广播居民移动/社交事件
  ├── models/resident.py       # status 枚举扩展, home_tile
  ├── services/sbti_service.py # 供演化系统调用 match_type()
  └── routers/admin/           # AgentLoop 监控面板

frontend/src/
  ├── components/ChatDrawer.tsx # 媒体上传 UI + 渲染
  ├── game/GameScene.ts        # 居民移动动画 + 新状态视觉
  ├── game/StatusVisuals.ts    # walking/socializing 动画
  └── stores/gameStore.ts      # 居民状态/活动追踪
```
