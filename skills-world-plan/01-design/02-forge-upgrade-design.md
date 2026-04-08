# Skills-World 炼化系统升级 + 角色统一设计

> 日期：2026-04-08
> 状态：待审核
> 前置文档：`2026-04-06-skills-world-design.md`

---

## 1. 设计目标

将 Skills-World 的炼化系统从"5 步引导式对话"升级为"自动调研 + 三重验证 + 双 Agent 精炼"的完整蒸馏管线，同时统一玩家与居民的数据模型，使每个在线用户都是一个"有人设的角色"。

### 核心变更

| 维度 | 现状 | 目标 |
|------|------|------|
| 炼化管线 | 5 步对话 → 直接 LLM 生成 | 智能路由 → 6 路调研 → 三重验证 → 构建 → 验证 → 精炼 |
| 角色模型 | User ≠ Resident（玩家无人设） | User 拥有绑定 Resident（玩家 = 角色） |
| 对话系统 | 仅 Player→NPC | Player↔NPC + Player↔Player（自动/手动） |
| 视觉系统 | 所有玩家同一精灵 | AI 头像 + 模板精灵智能匹配 |

---

## 2. 炼化管线架构

### 2.1 管线式架构（Pipeline-Centric）

```
InputRouter → [ResearchStage] → ExtractionStage → BuildStage → ValidationStage → RefinementStage → Output
               ↑ 仅深度蒸馏
```

每个 Stage 是独立 Service，通过 `ForgeSession` 状态机串联。中间产物持久化到数据库，支持断点续炼。

### 2.2 双轨模式

#### 快速炼化（适合虚构角色、个人/朋友、简单人设）

```
用户输入（名字 + 描述/对话引导）
    ↓
BuildStage（基于用户输入生成三层人设，单次 LLM 调用）
    ↓
轻量评分（现有 1-3 星自动评分）
    ↓
输出
```

- 耗时：30-60 秒
- Token 消耗：低（单次 LLM 调用）
- 注意：跳过 Research/Extraction/Validation/Refinement，心智模型由 LLM 直接推断而非三重验证

#### 深度蒸馏（适合公众人物、名人、知名虚构角色）

```
InputRouter（智能判断人物类型）
    ↓
ResearchStage（6 路并行调研）
    ↓ 调研检查点：展示来源摘要，用户确认
ExtractionStage（三重验证提取心智模型）
    ↓
BuildStage（三层人设构建）
    ↓
ValidationStage（三问验证 + 边缘测试 + 风格检测）
    ↓
RefinementStage（双 Agent 精炼）
    ↓
输出
```

- 耗时：2-5 分钟
- Token 消耗：高（6 路搜索 + 多轮 LLM 调用）

### 2.3 智能路由规则

`InputRouter` 自动判断走哪条轨道：

| 输入特征 | 路由结果 |
|---------|---------|
| 可搜索的公众人物名（"乔布斯""萧炎"） | 深度蒸馏（网络调研） |
| 公众人物名 + 用户提供的大段素材 | 深度蒸馏（素材优先 + 网络补充） |
| 非公众人物 + 有素材（"我朋友小明" + 经历文本） | 快速炼化（基于素材提取） |
| 虚构角色描述（"一个赛博朋克黑客"） | 快速炼化（引导式对话） |
| 导入外部 Skill 文件 | 格式检测 → 转换 → 快速炼化补全 |

判断逻辑：LLM 分类调用（轻量模型），判断输入是否为"可网络搜索到足够资料的人物"。

### 2.4 6 路调研（ResearchStage）

搜索后端：**SearXNG**（自建，`http://100.93.72.102:58080`）

6 个调研维度：

| 维度 | 搜索目标 | 输出 |
|------|---------|------|
| writings | 著作、文章、论文 | 核心观点和思想 |
| conversations | 访谈、播客、演讲 | 原话和语境 |
| expression_dna | 社交媒体、短内容 | 说话风格和用词习惯 |
| external_views | 第三方评价、传记 | 外部视角 |
| decisions | 关键决策、转折点 | 决策逻辑 |
| timeline | 成长历程、里程碑 | 时间线 |

每个维度执行 2 条搜索查询，取 top 5 结果。串行执行（间隔 1 秒），避免并发压垮 SearXNG。

当用户提供了本地素材时：
- 素材作为**一级来源**（权重最高）
- 网络调研仅补充素材未覆盖的维度

### 2.5 三重验证（ExtractionStage）

从调研数据中提取心智模型时，每个候选模型必须通过三重验证：

1. **跨域复现** — 在 2 个以上不同领域/场景中出现
2. **生成力** — 能预测该人物对新问题的立场
3. **排他性** — 不是"所有聪明人都会这么想"的泛化模式

通过 3 项 → 核心心智模型
通过 1-2 项 → 决策启发式
通过 0 项 → 丢弃

### 2.6 质量验证（ValidationStage）

深度蒸馏专用，4 个检验：

1. **三问验证** — 3 个该人物有已知答案的问题，验证回答是否符合
2. **边缘测试** — 1 个该人物从未公开讨论的问题，验证是否表现出适度不确定
3. **风格检测** — 100 字风格测试，验证表达 DNA 是否到位
4. **双 Agent 精炼** — 两个 Agent（优化者 + 创造者视角）独立审阅，提出改进建议

### 2.7 LLM 配置

| 用途 | 模型 | 接口 |
|------|------|------|
| 路由分类 | MiniMax-M2.5 | DashScope Anthropic 兼容 |
| 调研摘要 | MiniMax-M2.5 | 同上 |
| 三层生成 | MiniMax-M2.5 | 同上 |
| 质量验证 | MiniMax-M2.5 | 同上 |
| 头像生成 | gemini-3-pro-image-preview | Vertex AI via new-api |

---

## 3. 扩展三层输出格式

将 nuwa-skill 的 11 节内容分配进现有三层框架：

### Ability Layer（能力层）

```markdown
# Ability Layer

## 核心心智模型
3-5 个经三重验证的思维模型
每个包含：名称、一句话描述、跨域证据（2+ 场景）、应用方式、局限性

## 决策启发式
5-8 条 "if X then Y" 规则
每条附具体案例

## 专业技能
核心能力清单（战斗技能/专业领域/生活技能）
```

来源：nuwa-skill 的"核心心智模型" + "决策启发式" + 原 Ability 层内容

### Persona Layer（人格层）

```markdown
# Persona Layer

## 身份卡
50 字第一人称自我介绍

## 表达 DNA
说话风格、口头禅、句式偏好、幽默类型、确定性水平、引用习惯

## Layer 0: 核心性格（不可变）
底层性格特征

## Layer 1: 身份认同
如何定义自己

## Layer 2: 表达风格
具体语言模式

## Layer 3: 决策与判断
面对选择时的行为模式

## Layer 4: 人际行为
与他人互动的模式
```

来源：nuwa-skill 的"身份卡" + "表达 DNA" + 原 Persona 5 层模型

### Soul Layer（灵魂层）

```markdown
# Soul Layer

## Layer 0: 核心价值观（不可变）
最底层信念

## Layer 1: 人生经历与背景
关键经历 + 时间线

## Layer 2: 兴趣与审美
偏好、品味、文化取向

## Layer 3: 情感模式
情感表达风格、依恋类型

## Layer 4: 适应性与成长
面对困境的应对方式

## 智识谱系（可选）
谁影响了 TA，TA 影响了谁
```

来源：nuwa-skill 的"价值观与反模式" + "人物时间线" + "智识谱系" + 原 Soul 层内容

### Meta（元数据，跨层附加）

```markdown
# Meta

## 诚实边界
- 角色扮演的局限性
- 公开表达 ≠ 私下想法
- 信息截止说明

## 调研来源摘要
一级来源 vs 二级来源

## 炼化参数
模式（快速/深度）、调研条数、验证得分、精炼轮次
```

---

## 4. 角色统一架构

### 4.1 核心变更：User 绑定 Player Resident

每个 User 自动拥有一个 `type="player"` 的 Resident 记录，共用三层人设系统。

```
User (账户)
  └── Resident (type="player")    ← 玩家自己的角色
  └── Resident (type="npc") × N   ← 玩家炼化的 NPC 居民
```

**Resident 模型新增字段：**

```python
# 区分玩家角色和 NPC
resident_type: str  # "player" | "npc"，默认 "npc"

# 回复模式（仅 player 类型使用）
reply_mode: str  # "manual" | "auto"，默认 "manual"
```

**User 模型新增字段：**

```python
# 绑定玩家角色
player_resident_id: str | None  # FK → Resident.id
```

### 4.2 新手引导流程

注册/首次登录后，进入角色创建引导（在进入游戏世界之前）：

```
Step 1: 选择创建方式
├── A) 从零创建（输入名字 → 描述性格技能 → 系统生成三层人设）
├── B) 加载预设人物（从萧炎、乔布斯等预设列表选择）
├── C) 导入 Skill 文件（上传/粘贴 Markdown）
│   └── 格式检测 → 不符合则提示"将自动转换为标准格式" → LLM 转换
└── D) 跳过（系统分配默认人设，后续可修改）

Step 2: 选择/确认精灵图（从 25 个基础模板中选）

Step 3: 选择回复模式（自动/手动，随时可切换）

Step 4: 进入游戏世界
```

### 4.3 Skill 格式转换管线

当用户导入的 Skill 不符合三层格式时：

```
输入 Skill 文本
    ↓
格式检测（LLM 判断：标准三层 / nuwa-skill 11 节 / colleague-skill 2 层 / 纯文本）
    ↓
如果非标准格式：
    ↓
提示用户"检测到 [格式名]，将自动转换为标准三层格式"
    ↓
LLM 转换（映射到 Ability + Persona + Soul + Meta）
    ↓
用户预览确认
    ↓
保存为标准 Resident
```

### 4.4 对话系统扩展

#### 消息路由

```
发送消息
    ↓
判断目标类型
├── 目标是 NPC (type="npc")
│   └── LLM + NPC 人设 → 回复（现有逻辑）
├── 目标是 Player (type="player")
│   ├── 目标在线 + 手动模式 → WebSocket 推送给目标用户
│   ├── 目标在线 + 自动模式 → LLM + 目标人设 → 回复
│   └── 目标离线 + 自动模式 → LLM + 目标人设 → 回复（异步）
│   └── 目标离线 + 手动模式 → 消息排队，上线后推送
```

#### WebSocket 新消息类型

```typescript
// 玩家间对话
{ type: "player_chat", target_id: string, text: string }
{ type: "player_chat_reply", from_id: string, text: string, is_auto: boolean }

// 回复模式切换
{ type: "set_reply_mode", mode: "auto" | "manual" }
```

#### Token 消耗归属

| 场景 | 付费方 |
|------|--------|
| 玩家主动对话 NPC | 发起方 |
| 玩家主动对话自动模式玩家 | 发起方 |
| NPC 主动搭话玩家（未来功能） | 系统承担 |

---

## 5. 视觉分层系统

### 5.1 头像/立绘层

**用途**：对话界面、角色卡、炼化预览、个人资料

**生成方式**：
- 模型：`gemini-3-pro-image-preview`（Vertex AI 通道）
- 接口：`http://100.93.72.102:3000/v1`
- 触发时机：角色创建/炼化完成后自动生成
- Prompt 模板：基于三层人设中的外观描述、身份卡、核心性格生成 Q 版头像

**存储**：
- `Resident.portrait_url` — 头像图 URL（新增字段）
- 存储到对象存储或本地 `static/portraits/`

### 5.2 地图精灵层

**用途**：游戏世界中的 32×32 行走动画

**生成方式**：从 25 个基础精灵模板中智能匹配

匹配逻辑：
```
角色人设 → LLM 提取外观特征（性别、年龄段、气质类型）
    ↓
特征匹配 25 个模板的预标注属性
    ↓
选择最匹配的模板作为 sprite_key
    ↓
（可选）程序化调色：基于人设中的标志色调整发色/服装色
```

25 个模板预标注示例：
```json
{
  "埃迪": { "gender": "male", "age": "young", "vibe": "casual" },
  "伊莎贝拉": { "gender": "female", "age": "young", "vibe": "elegant" },
  "克劳斯": { "gender": "male", "age": "mature", "vibe": "serious" },
  ...
}
```

**用户可在角色创建 Step 2 手动覆盖自动匹配结果。**

### 5.3 出生点

- 首次登录：中央广场附近随机偏移（半径 5 格内）
- 后续登录：恢复上次下线位置（新增 `User.last_x`, `User.last_y` 字段）
- 掉线保护：断开连接时自动保存当前位置

---

## 6. 预设虚拟人物

### 6.1 来源

| 来源 | 人物 | 数量 |
|------|------|------|
| nuwa-skill 示例 | Steve Jobs, Elon Musk, Charlie Munger, Feynman, Naval, Taleb, Paul Graham, Zhang Yiming, Karpathy, Ilya Sutskever, MrBeast, Trump, Zhang Xuefeng | 13 |
| MVP 测试 | 萧炎（《斗破苍穹》） | 1 |
| 合计 | | 14 |

### 6.2 导入策略

nuwa-skill 的 11 节格式 → 自动转换为扩展三层格式：

| nuwa-skill 节 | 目标层 |
|---------------|--------|
| 核心心智模型 | Ability.核心心智模型 |
| 决策启发式 | Ability.决策启发式 |
| 身份卡 | Persona.身份卡 |
| 表达 DNA | Persona.表达 DNA |
| 价值观与反模式 | Soul.Layer 0 核心价值观 |
| 人物时间线 | Soul.Layer 1 人生经历 |
| 智识谱系 | Soul.智识谱系 |
| 诚实边界 | Meta.诚实边界 |
| 调研来源 | Meta.调研来源摘要 |
| 回答工作流 | Meta.炼化参数（存为 Agentic Protocol 配置） |

### 6.3 研究数据保留

nuwa-skill 每个角色的 `references/research/` 目录（6 类调研文件）保留为"蒸馏素材库"，用户在深度蒸馏时可选择基于已有调研数据生成定制版本。

存储路径：`backend/data/research_corpus/{person-slug}/`

---

## 7. LinuxDo OAuth2 登录

### 7.1 概述

新增 LinuxDo（linux.do）作为第三方登录方式，与现有的邮箱注册/登录和 GitHub OAuth 并列。采用标准 Authorization Code Grant 流程，直接在 FastAPI 后端实现，不依赖 ld-oauth2 中间代理。

### 7.2 OAuth2 端点

| 用途 | URL |
|------|-----|
| 授权 | `https://connect.linux.do/oauth2/authorize` |
| 换 Token | `https://connect.linux.do/oauth2/token` |
| 用户信息 | `https://connect.linux.do/api/user` |

认证方式：Token 端点使用 HTTP Basic Auth（`client_id:client_secret` 放 Header）。

### 7.3 用户信息字段

```json
{
  "id": 12345,           // LinuxDo 用户 ID
  "username": "string",  // 登录名
  "name": "string",      // 显示名
  "active": true,        // 账户是否激活
  "trust_level": 2,      // Discourse 信任等级 (0-4)
  "silenced": false      // 是否被禁言
}
```

### 7.4 登录流程

```
前端                          后端                          LinuxDo
  │                             │                              │
  │  GET /auth/linuxdo/login    │                              │
  │ ──────────────────────────> │                              │
  │  302 → connect.linux.do     │                              │
  │     /oauth2/authorize       │                              │
  │ <────────────────────────── │                              │
  │                             │                              │
  │  用户在 LinuxDo 授权         │                              │
  │ ────────────────────────────────────────────────────────> │
  │                             │                              │
  │                             │  callback?code=XXX&state=YYY │
  │                             │ <─────────────────────────── │
  │                             │                              │
  │                             │  POST /oauth2/token          │
  │                             │  (Basic Auth)                │
  │                             │ ────────────────────────────>│
  │                             │  { access_token }            │
  │                             │ <────────────────────────────│
  │                             │                              │
  │                             │  GET /api/user               │
  │                             │  (Bearer token)              │
  │                             │ ────────────────────────────>│
  │                             │  { id, username, name, ... } │
  │                             │ <────────────────────────────│
  │                             │                              │
  │  302 → 前端?token=JWT       │                              │
  │ <────────────────────────── │                              │
```

### 7.5 用户匹配逻辑

```python
# 1. 用 linuxdo_id 查找已有用户
user = db.query(User).filter(User.linuxdo_id == str(ld_user["id"])).first()

# 2. 如果没找到，尝试用 username 生成 email 占位符查找
#    （LinuxDo 不返回 email，用 "{username}@linux.do" 作为占位）

# 3. 都没有 → 创建新用户
user = User(
    name=ld_user["name"] or ld_user["username"],
    email=f"{ld_user['username']}@linux.do",  # 占位 email
    linuxdo_id=str(ld_user["id"]),
    linuxdo_trust_level=ld_user["trust_level"],
    soul_coin_balance=100,  # 注册奖励
)
```

### 7.6 安全要求

- **state 参数**：每次授权请求生成随机 state，存入 Redis/Cookie，回调时验证（防 CSRF）
- **仅接受 active=true 的用户**：silenced 或 inactive 用户拒绝登录
- **trust_level 可选门槛**：可配置最低 trust_level（如 ≥1），防止新注册垃圾账户

---

## 8. 管理面板（Admin Panel）

### 8.1 技术方案

在现有 React 前端中新增 `/admin` 路由区域，复用现有技术栈和 API 客户端。

**权限模型：**
- User 模型新增 `is_admin: bool = False` 字段
- 所有 `/admin/*` API 端点通过中间件校验 `is_admin`
- 前端路由守卫：非 admin 用户访问 `/admin` 重定向到首页
- 首个 admin 通过数据库手动设置或 CLI 命令创建

**布局：**
```
┌──────────────────────────────────────────────┐
│  Skills-World Admin          [用户名] [退出] │
├────────┬─────────────────────────────────────┤
│        │                                     │
│ 仪表盘 │          内容区域                    │
│ 用户   │                                     │
│ 居民   │                                     │
│ 炼化   │                                     │
│ 经济   │                                     │
│ 系统   │                                     │
│        │                                     │
├────────┴─────────────────────────────────────┤
│  Skills-World v1.0                           │
└──────────────────────────────────────────────┘
```

左侧固定导航栏 + 右侧内容区，标准后台布局。

### 8.2 模块一：仪表盘（Dashboard）

路由：`/admin`

**实时指标卡片（4 个）：**

| 指标 | 数据来源 | 刷新频率 |
|------|---------|---------|
| 当前在线用户 | WebSocket ConnectionManager.active 长度 | 实时（WS 推送） |
| 今日新注册 | `SELECT COUNT(*) FROM users WHERE created_at >= today` | 30 秒轮询 |
| 活跃对话数 | ConnectionManager.chatting 长度 | 实时（WS 推送） |
| Soul Coin 净流通量 | `SUM(amount) FROM transactions WHERE created_at >= today` | 30 秒轮询 |

**图表区域：**
- 7 日用户增长趋势（折线图）
- 7 日对话量趋势（柱状图）
- Soul Coin 收支比（环形图：发放 vs 消耗）
- 热门居民 Top 10（水平条形图，按 heat 排序）

**快捷操作：**
- 查看最近注册用户（5 条）
- 查看最近炼化记录（5 条）
- SearXNG 状态灯（绿/红，ping 检测）
- LLM API 状态灯（绿/红，健康检查）

### 8.3 模块二：用户管理（Users）

路由：`/admin/users`

**列表页：**

| 列 | 内容 | 可排序 | 可筛选 |
|----|------|--------|--------|
| 用户名 | name | 是 | 搜索 |
| 邮箱 | email | 否 | 搜索 |
| 登录方式 | 邮箱/GitHub/LinuxDo 图标 | 否 | 多选筛选 |
| Soul Coin | soul_coin_balance | 是 | 范围筛选 |
| 创建居民数 | COUNT(residents) | 是 | - |
| 注册时间 | created_at | 是 | 日期范围 |
| 状态 | active/banned | 否 | 筛选 |
| 操作 | 详情/调整余额/封禁 | - | - |

分页：每页 20 条，服务端分页。

**用户详情页** `/admin/users/{id}`：

```
基本信息卡片
├── 头像、姓名、邮箱
├── 登录方式（邮箱 ✓ / GitHub ✓ / LinuxDo ✓ trust_level=2）
├── 注册时间、最后活跃时间
└── Soul Coin 余额 [+调整]

Tab 1: 创建的居民
├── 居民列表（名称、街区、评分、热度）
└── 点击跳转居民详情

Tab 2: 对话记录
├── 对话列表（居民名、开始时间、轮次、评分）
└── 展开可查看消息内容

Tab 3: 交易流水
├── 时间、金额（+/-）、原因
└── 筛选：类型（充值/消耗/奖励）

Tab 4: 玩家角色
├── 绑定的 Player Resident 信息
├── 三层人设预览
├── 回复模式（自动/手动）
└── 精灵图 + 头像预览
```

**操作：**
- **调整余额**：弹窗输入金额（正/负）+ 原因，创建 Transaction 记录
- **封禁/解封**：设置 `is_banned` 字段，封禁后 JWT 校验拒绝
- **设为管理员**：设置 `is_admin = True`
- **重置密码**：生成临时密码（仅邮箱登录用户）

### 8.4 模块三：居民管理（Residents）

路由：`/admin/residents`

**列表页：**

| 列 | 内容 | 可排序 | 可筛选 |
|----|------|--------|--------|
| 名称 | name + sprite 缩略图 | 是 | 搜索 |
| 类型 | NPC / Player | 否 | 筛选 |
| 街区 | district | 否 | 多选筛选 |
| 评分 | star_rating (1-3★) | 是 | 筛选 |
| 热度 | heat | 是 | 范围 |
| 状态 | idle/chatting/popular/sleeping | 否 | 多选筛选 |
| 创建者 | creator.name | 否 | 搜索 |
| 对话数 | total_conversations | 是 | - |
| 创建时间 | created_at | 是 | 日期范围 |

**居民详情页** `/admin/residents/{slug}`：

```
基本信息
├── 头像（AI 生成）+ 精灵图预览
├── 名称、slug、街区、状态、热度
├── 创建者（链接到用户详情）
├── 评分：★★☆ (2/3) | 对话数: 47 | 平均评分: 4.2
└── 地图位置：(tile_x, tile_y)

Tab 1: 三层人设
├── Ability Layer（Markdown 渲染 + 编辑按钮）
├── Persona Layer（Markdown 渲染 + 编辑按钮）
├── Soul Layer（Markdown 渲染 + 编辑按钮）
└── Meta（诚实边界、调研来源、炼化参数）

Tab 2: 对话统计
├── 对话量趋势（7日/30日）
├── 评分分布（1-5星饼图）
└── 最近对话列表

Tab 3: 版本历史
├── 版本列表（时间、修改摘要）
└── 版本对比（diff 视图）
```

**预设人物管理** `/admin/residents/presets`：
- 14 个预设人物的专用管理页
- 支持：编辑三层数据、更新调研素材、重新生成头像
- 新增预设：可从现有居民"提升"为预设，或直接导入 nuwa-skill 格式

**批量操作：**
- 批量调整街区
- 批量重新评分（触发 scoring_service）
- 批量状态重置（如将所有 sleeping 改为 idle）

### 8.5 模块四：炼化监控（Forge Monitor）

路由：`/admin/forge`

**活跃会话面板：**

| 列 | 内容 |
|----|------|
| 会话 ID | forge_id |
| 用户 | creator name（链接） |
| 目标人物 | character_name |
| 模式 | 快速 / 深度 |
| 当前阶段 | routing → researching → extracting → building → validating → refining → done |
| 阶段进度 | 进度条（如 researching 3/6 维度完成） |
| 已耗时 | 实时计时 |
| Token 已用 | 累计 input + output tokens |

**历史记录页：**

| 列 | 可筛选 |
|----|--------|
| 状态（done/error/cancelled） | 多选 |
| 模式（快速/深度） | 多选 |
| 创建时间 | 日期范围 |
| 总耗时 | 范围 |
| Token 消耗 | 范围 |

点击展开可查看：
- 各阶段耗时明细
- 调研结果摘要（搜索条数、来源分布）
- 验证报告（三问验证结果、风格检测得分）
- 精炼日志（双 Agent 建议）

**SearXNG 健康监控：**
- 最近 1 小时搜索成功率
- 平均响应时间
- 引擎可用状态（Brave ✓ / DuckDuckGo ✓ / Startpage ✗）
- 手动 ping 测试按钮

### 8.6 模块五：经济系统（Economy）

路由：`/admin/economy`

**全局统计卡片：**
- Soul Coin 总发行量（所有正向 transaction 之和）
- Soul Coin 总消耗量（所有负向 transaction 之和）
- 净流通量（总发行 - 总消耗）
- 用户平均余额

**交易流水表：**

| 列 | 可筛选 |
|----|--------|
| 时间 | 日期范围 |
| 用户 | 搜索 |
| 金额 | 正/负/范围 |
| 原因 | 类型筛选（signup_bonus / daily_reward / chat / forge_creation / creator_passive / good_rating） |

**参数配置面板：**

所有经济参数集中配置，修改后即时生效（写入数据库配置表，不需要重启服务）：

```
┌─ Soul Coin 参数配置 ──────────────────────────┐
│                                                │
│  注册奖励          [100] SC                    │
│  每日登录奖励      [  5] SC                    │
│  对话默认成本/轮   [  1] SC                    │
│  创建居民奖励      [ 50] SC                    │
│  创作者被动收益/轮  [  1] SC                    │
│  高评分奖励        [  5] SC（≥ [4] 星触发）     │
│                                                │
│                          [恢复默认]  [保存]     │
└────────────────────────────────────────────────┘
```

### 8.7 模块六：系统配置（System Config）

路由：`/admin/system`

**分组配置面板：**

#### LLM 配置

LLM 调用分为**系统 LLM**（平台承担）和**用户 LLM**（可由用户自带 Key）两类。

**调用归属：**

| 归属 | 调用场景 | 特征 |
|------|---------|------|
| 系统 LLM | 智能路由判断、质量评分（1-3星）、街区分配、Skill 格式检测、精灵图匹配、预设角色初始炼化 | 轻量（<500 token/次）、平台基础设施 |
| 用户 LLM | 对话（NPC/玩家）、炼化全流程（生成+验证+精炼）、Skill 格式转换、AI 头像生成 | 重量（500-30000 token/次）、用户直接受益 |

```
┌─ 系统 LLM ────────────────────────────────────────────────────┐
│                                                                │
│  ── 基础配置 ──                                                │
│  模型              [MiniMax-M2.5           ▼]                  │
│  API Base URL      [https://coding.dashscope...]               │
│  API Key           [sk-sp-****...****bd0b2] [显示/隐藏]        │
│                                                                │
│  ── 生成参数 ──                                                │
│  max_tokens（路由/评分）  [ 200]                                │
│  max_tokens（街区分配）   [ 100]                                │
│  Temperature             [ 0.3]   （系统调用偏低温，确定性高）   │
│                                                                │
│  ── 高级参数 ──                                                │
│  启用 Thinking     [✗ 关闭]   （系统轻量调用不需要深度推理）     │
│  请求超时          [  30] 秒                                   │
│  最大重试次数      [   2]                                       │
│  Fallback 模型     [qwen3.5-plus           ▼] [✗ 未启用]      │
│  Fallback 触发条件  ○ 主模型超时  ○ 主模型报错  ● 两者皆触发    │
│                                                                │
└────────────────────────────────────────────────────────────────┘

┌─ 用户 LLM（默认）──────────────────────────────────────────────┐
│                                                                │
│  ── 基础配置 ──                                                │
│  模型              [MiniMax-M2.5           ▼]                  │
│  API Base URL      [https://coding.dashscope...]               │
│  API Key           [sk-sp-****...****bd0b2] [显示/隐藏]        │
│                                                                │
│  ── 生成参数 ──                                                │
│  max_tokens（对话）       [  512]                               │
│  max_tokens（Ability）    [1500]                                │
│  max_tokens（Persona）    [2000]                                │
│  max_tokens（Soul）       [1500]                                │
│  max_tokens（快速炼化）   [4096]                                │
│  Temperature（对话）      [ 0.7]                                │
│  Temperature（炼化）      [ 0.5]                                │
│                                                                │
│  ── 高级参数 ──                                                │
│  启用 Thinking     [✓ 开启]   思考 token 预算 [8192]           │
│  请求超时          [ 120] 秒                                   │
│  最大重试次数      [   3]                                       │
│  并发限制          [   5] 个同时请求（防止 API 限流）           │
│  Fallback 模型     [qwen3.5-plus           ▼] [✓ 已启用]      │
│  Fallback 触发条件  ○ 主模型超时  ○ 主模型报错  ● 两者皆触发    │
│                                                                │
│  ── 深度蒸馏专用 ──                                            │
│  调研阶段并发数    [   2] （SearXNG 查询并发，避免限流）        │
│  调研查询间隔      [   1] 秒                                   │
│  验证阶段模型      [与主模型相同  ▼]  （可选择更强模型做验证）   │
│  精炼阶段模型      [与主模型相同  ▼]                            │
│                                                                │
└────────────────────────────────────────────────────────────────┘

┌─ 头像生成 LLM ─────────────────────────────────────────────────┐
│                                                                │
│  模型              [gemini-3-pro-image-preview ▼]              │
│  API Base URL      [http://100.93.72.102:3000/v1]              │
│  API Key           [sk-JH****...****RetP] [显示/隐藏]          │
│  请求超时          [ 180] 秒                                   │
│  Fallback 模型     [gemini-3.1-flash-image-preview ▼] [✓]     │
│                                                                │
└────────────────────────────────────────────────────────────────┘

┌─ 用户自定义 LLM 策略 ─────────────────────────────────────────┐
│                                                                │
│  允许用户自带 API Key    [✗ 关闭]                              │
│                                                                │
│  开启后：                                                      │
│  ├─ 用户可在个人设置中填写自己的 API Key / Base URL / Model    │
│  ├─ 用户 LLM 调用优先使用用户自己的 Key                        │
│  ├─ 用户未配置时 fallback 到系统默认用户 LLM                   │
│  ├─ 系统 LLM 调用始终使用系统 Key（不受影响）                  │
│  └─ 对话/炼化不扣 Soul Coin（用户自付 API 费用）               │
│                                                                │
│  允许的 API 格式   [✓] OpenAI 兼容  [✓] Anthropic 兼容        │
│  用户 Key 验证     [✓ 启用] （填写时自动发送测试请求验证可用）  │
│  用户可选模型白名单 [留空则不限制]                              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### 热度与状态规则
```
Popular 热度阈值    [ 50] 次对话/7天
Sleeping 无活动天数  [  7] 天
热度计算 Cron 间隔   [3600] 秒
```

#### 评分规则
```
最低内容长度/层      [ 50] 字符
3星最低对话数        [ 50] 次
3星最低平均评分      [3.5]
```

#### 版本控制
```
最大保留版本数       [ 10]
```

#### 街区地图配置
```
┌─ engineering ─────────────────┐
│ 基准坐标: (58, 55)            │
│ 槽位数: 20                    │
│ [编辑坐标...]                 │
├─ product ─────────────────────┤
│ 基准坐标: (35, 40)            │
│ 槽位数: 20                    │
│ [编辑坐标...]                 │
├─ academy ─────────────────────┤
│ 基准坐标: (30, 65)            │
│ 槽位数: 20                    │
│ [编辑坐标...]                 │
├─ free ────────────────────────┤
│ 基准坐标: (100, 38)           │
│ 槽位数: 20                    │
│ [编辑坐标...]                 │
└───────────────────────────────┘
默认出生点: ([76], [50])
```

#### OAuth 状态
```
邮箱登录            [✓ 启用]
GitHub OAuth        [✗ 未配置] client_id: (empty)
LinuxDo OAuth       [? 待配置] client_id: (empty)
LinuxDo 最低信任等级 [  1]
```

注意：OAuth secret 不在面板显示或修改，仅通过环境变量/密钥管理配置。

#### 精灵模板管理
```
┌─ 25 个模板 ───────────────────────────────────┐
│ [sprite] 伊莎贝拉  female / young / elegant    │
│ [sprite] 克劳斯    male / mature / serious     │
│ [sprite] 亚当      male / young / casual       │
│ ... (每个可编辑属性标注)                        │
│                                                │
│ [+ 上传新模板]                                  │
└────────────────────────────────────────────────┘
```

### 8.8 Admin API 端点

```
# 仪表盘
GET    /admin/dashboard/stats         # 实时指标
GET    /admin/dashboard/trends        # 7日趋势数据
GET    /admin/dashboard/health        # 服务健康状态

# 用户管理
GET    /admin/users                   # 用户列表（分页/筛选/排序）
GET    /admin/users/{id}              # 用户详情
PATCH  /admin/users/{id}              # 修改用户（余额/封禁/admin）
POST   /admin/users/{id}/adjust-coin  # 调整余额（带原因）

# 居民管理
GET    /admin/residents               # 居民列表（分页/筛选/排序）
GET    /admin/residents/{slug}        # 居民详情
PATCH  /admin/residents/{slug}        # 修改居民
POST   /admin/residents/batch         # 批量操作
GET    /admin/residents/presets       # 预设人物列表
POST   /admin/residents/presets       # 新增预设
PUT    /admin/residents/presets/{slug} # 更新预设

# 炼化监控
GET    /admin/forge/active            # 活跃炼化会话
GET    /admin/forge/history           # 历史记录（分页/筛选）
GET    /admin/forge/{id}/detail       # 会话详情（各阶段数据）
GET    /admin/forge/searxng-health    # SearXNG 健康检查

# 经济系统
GET    /admin/economy/stats           # 经济统计
GET    /admin/economy/transactions    # 交易流水（分页/筛选）
GET    /admin/economy/config          # 获取经济参数
PUT    /admin/economy/config          # 更新经济参数

# 系统配置
GET    /admin/config/{group}          # 获取配置组（llm/heat/scoring/districts/oauth/sprites）
PUT    /admin/config/{group}          # 更新配置组
GET    /admin/config/sprites          # 精灵模板列表
PUT    /admin/config/sprites/{key}    # 更新模板属性
POST   /admin/config/sprites          # 上传新模板
```

### 8.9 动态配置存储

当前所有参数都是硬编码常量或 .env 环境变量（修改需重启）。管理面板需要支持**运行时动态配置**。

**方案：新增 SystemConfig 模型**

```python
class SystemConfig(Base):
    __tablename__ = "system_config"
    key: str        # 配置键，如 "economy.signup_bonus"
    value: str      # JSON 序列化的值
    group: str      # 分组：economy / heat / scoring / llm / districts / sprites
    updated_at: datetime
    updated_by: str # 修改人 user_id
```

**配置读取优先级：**
```
数据库 SystemConfig（运行时可改） > .env 环境变量 > 代码默认值
```

启动时加载到内存缓存，管理面板修改后刷新缓存，无需重启服务。

---

## 9. 用户设置面板（User Settings）

路由：`/settings`

普通用户的个人设置页，包含 5 个分组。

### 9.1 账户设置

```
┌─ 账户 ─────────────────────────────────────────┐
│                                                  │
│  显示名称     [萧炎] [保存]                       │
│                                                  │
│  邮箱         xiaoyan@linux.do (不可修改)         │
│                                                  │
│  修改密码     [当前密码] [新密码] [确认] [保存]     │
│  (仅邮箱注册用户显示)                              │
│                                                  │
│  ── 第三方账号绑定 ──                              │
│  GitHub       [✗ 未绑定]  [去绑定]                │
│  LinuxDo      [✓ 已绑定]  trust_level: 2  [解绑]  │
│                                                  │
│  ── 危险操作 ──                                   │
│  [注销账号]  (需输入密码或二次确认)                 │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 9.2 角色设置

```
┌─ 我的角色 ─────────────────────────────────────────────────────┐
│                                                                │
│  [头像预览]  [精灵图预览]                                       │
│                                                                │
│  角色名     [萧炎] [保存]                                       │
│                                                                │
│  ── 精灵图 ──                                                  │
│  当前: [克劳斯]                                                │
│  [25 个精灵图缩略选择网格]  [保存]                              │
│                                                                │
│  ── 头像 ──                                                    │
│  [当前 AI 头像]                                                 │
│  [重新生成]  [上传自定义]                                       │
│                                                                │
│  ── 三层人设 ──                                                │
│  Ability Layer  [查看] [编辑]                                   │
│  Persona Layer  [查看] [编辑]                                   │
│  Soul Layer     [查看] [编辑]                                   │
│  (编辑后自动保存版本快照)                                       │
│                                                                │
│  ── 快捷操作 ──                                                │
│  [重新炼化角色]  — 重新走炼化流程覆盖当前人设                    │
│  [导入 Skill]   — 上传/粘贴 Skill 文件替换当前人设              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 9.3 互动设置

```
┌─ 互动 ─────────────────────────────────────────────────────────┐
│                                                                │
│  ── 回复模式 ──                                                │
│  当前模式:  ○ 手动（自己打字回复）                               │
│            ● 自动（LLM 基于你的人设代为回复）                    │
│                                                                │
│  ── 离线行为 ──                                                │
│  离线时允许 LLM 代替回复    [✓ 开启]                            │
│  (关闭后，离线时其他玩家对你发的消息将排队，上线后推送)            │
│                                                                │
│  ── 通知 ──                                                    │
│  有人发起对话时弹窗提醒      [✓ 开启]                           │
│  仅手动模式时提醒            [✗ 关闭]                           │
│  创作的居民被对话时通知      [✓ 开启]                           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 9.4 隐私设置

```
┌─ 隐私 ─────────────────────────────────────────────────────────┐
│                                                                │
│  ── 地图可见性 ──                                              │
│  在地图上显示我的角色    [✓ 可见]                               │
│  (关闭后进入隐身模式，其他玩家看不到你)                          │
│                                                                │
│  ── 人设公开范围 ──                                            │
│  其他玩家可以看到:                                              │
│    ● 完整人设（Ability + Persona + Soul 全部公开）              │
│    ○ 仅身份卡（只显示 50 字简介）                               │
│    ○ 完全隐藏（其他玩家看不到你的人设）                          │
│                                                                │
│  ── 对话记录 ──                                                │
│  允许对话出现在居民统计中  [✓ 允许]                             │
│  (关闭后你与 NPC 的对话不计入居民的"最近对话"数据)               │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 9.5 LLM 设置（仅当管理员开启"允许用户自带 API Key"时显示）

```
┌─ 自定义 LLM ───────────────────────────────────────────────────┐
│                                                                │
│  启用自定义 LLM    [✗ 关闭]                                    │
│  (开启后，你的对话和炼化将使用你自己的 API Key，不扣 Soul Coin)  │
│                                                                │
│  API 格式     ○ OpenAI 兼容  ● Anthropic 兼容                  │
│  API Base URL [                                    ]           │
│  API Key      [                                    ]           │
│  模型名称     [                                    ]           │
│                                                                │
│  [测试连接]  → ✓ 连接成功，模型响应正常                         │
│                                                                │
│  ── 高级（可选）──                                             │
│  启用 Thinking     [✗ 关闭]                                    │
│  Temperature       [ 0.7]                                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 9.6 经济设置

```
┌─ Soul Coin ────────────────────────────────────────────────────┐
│                                                                │
│  当前余额: 🪙 347 Soul Coins                                  │
│                                                                │
│  低余额提醒阈值    [ 10] SC                                    │
│  (余额低于此值时弹窗提醒)                                       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 9.7 User Settings API 端点

```
GET    /settings                      # 获取所有用户设置
PATCH  /settings/account              # 修改账户信息（名称/密码）
POST   /settings/account/bind-github  # 绑定 GitHub
POST   /settings/account/bind-linuxdo # 绑定 LinuxDo
DELETE /settings/account/unbind/{provider} # 解绑第三方账号
DELETE /settings/account              # 注销账号

PATCH  /settings/character            # 修改角色（名称/精灵图）
PUT    /settings/character/persona    # 更新三层人设
POST   /settings/character/reforge    # 重新炼化
POST   /settings/character/import     # 导入 Skill
POST   /settings/character/avatar     # 重新生成/上传头像

PATCH  /settings/interaction          # 修改互动设置（回复模式/离线行为/通知）
PATCH  /settings/privacy              # 修改隐私设置（可见性/人设公开/对话记录）
PATCH  /settings/llm                  # 修改自定义 LLM 配置
POST   /settings/llm/test             # 测试自定义 LLM 连接
PATCH  /settings/economy              # 修改经济设置（余额提醒阈值）
```

---

## 10. 数据模型变更汇总

### Resident 模型新增

```python
resident_type: str = "npc"           # "player" | "npc"
reply_mode: str = "manual"           # "manual" | "auto"（仅 player 用）
portrait_url: str | None = None      # AI 生成的头像 URL
meta_json 扩展:
  - "honesty_boundaries": str        # 诚实边界
  - "research_sources": str          # 调研来源
  - "forge_mode": str                # "quick" | "deep"
  - "forge_score": dict              # 验证得分详情
```

### User 模型新增

```python
player_resident_id: str | None       # FK → Resident.id（绑定的玩家角色）
last_x: int = 2432                   # 上次下线位置 X（像素）
last_y: int = 1600                   # 上次下线位置 Y（像素）
linuxdo_id: str | None               # LinuxDo 用户 ID（unique, nullable）
linuxdo_trust_level: int | None      # LinuxDo 信任等级 (0-4)
is_admin: bool = False               # 管理员标识
is_banned: bool = False              # 封禁标识

# 用户设置
settings_json: JSON = {}             # 用户个人设置（互动/隐私/经济，结构见下方）

# 自定义 LLM（仅当系统开启 allow_user_custom_llm 时生效）
custom_llm_enabled: bool = False     # 是否启用自定义 LLM
custom_llm_api_format: str = "anthropic"  # "openai" | "anthropic"
custom_llm_api_key: str | None       # 用户 API Key（AES 加密存储）
custom_llm_base_url: str | None      # 用户自定义端点
custom_llm_model: str | None         # 用户选择的模型
```

**settings_json 结构：**

```json
{
  "interaction": {
    "reply_mode": "manual",
    "offline_auto_reply": true,
    "notify_on_chat": true,
    "notify_only_manual": false,
    "notify_creator_earnings": true
  },
  "privacy": {
    "map_visible": true,
    "persona_visibility": "full",
    "allow_conversation_stats": true
  },
  "economy": {
    "low_balance_alert": 10
  },
  "llm": {
    "thinking_enabled": false,
    "temperature": 0.7
  }
}
```

### ForgeSession 模型（新建）

```python
id: str                              # 会话 ID
user_id: str                         # FK → User.id
character_name: str                  # 炼化目标名
mode: str                            # "quick" | "deep"
status: str                          # "routing" | "researching" | "extracting" | "building" | "validating" | "refining" | "done" | "error"
current_stage: str                   # 当前阶段名
research_data: JSON                  # 调研原始数据
extraction_data: JSON                # 提取的心智模型等
build_output: JSON                   # 三层生成结果
validation_report: JSON              # 验证报告
refinement_log: JSON                 # 精炼日志
created_at: datetime
updated_at: datetime
```

### SystemConfig 模型（新建）

```python
key: str                              # 配置键，如 "economy.signup_bonus"（primary key）
value: str                            # JSON 序列化的值
group: str                            # 分组：economy / heat / scoring / llm / districts / sprites
updated_at: datetime
updated_by: str                       # 修改人 user_id
```

---

## 11. API 变更汇总

### 新增端点

```
GET    /auth/linuxdo/login            # LinuxDo OAuth2 授权跳转
GET    /auth/linuxdo/callback         # LinuxDo OAuth2 回调

POST   /forge/deep-start              # 启动深度蒸馏
POST   /forge/import-skill            # 导入外部 Skill（自动格式转换）
GET    /forge/deep-status/{id}        # 深度蒸馏进度查询（含阶段详情）
POST   /forge/deep-confirm/{id}       # 确认调研检查点，继续管线

POST   /onboarding/create-character   # 新手引导：创建玩家角色
POST   /onboarding/load-preset        # 新手引导：加载预设人物
POST   /onboarding/import-skill       # 新手引导：导入 Skill
POST   /onboarding/skip               # 新手引导：跳过

POST   /avatar/generate               # 生成 AI 头像
GET    /sprites/templates              # 获取 25 个精灵模板列表（含预标注属性）
POST   /sprites/match                  # 基于人设智能匹配精灵

GET    /presets                        # 获取预设人物列表
GET    /presets/{slug}                 # 获取预设人物详情（含三层数据）

# 用户设置（完整列表见 9.7 节）
GET    /settings                      # 获取所有用户设置
PATCH  /settings/account              # 修改账户信息
PATCH  /settings/character            # 修改角色设置
PATCH  /settings/interaction          # 修改互动设置
PATCH  /settings/privacy              # 修改隐私设置
PATCH  /settings/llm                  # 修改自定义 LLM
POST   /settings/llm/test             # 测试自定义 LLM 连接

# 管理面板（完整列表见 8.8 节）
GET    /admin/dashboard/stats         # 仪表盘实时指标
GET    /admin/users                   # 用户管理
GET    /admin/residents               # 居民管理
GET    /admin/forge/active            # 炼化监控
GET    /admin/economy/stats           # 经济统计
GET    /admin/config/{group}          # 系统配置读取
PUT    /admin/config/{group}          # 系统配置修改
```

### 修改端点

```
WebSocket handler 扩展:
  - 新消息类型: player_chat, player_chat_reply, set_reply_mode
  - 连接时使用 User.last_x/last_y 作为出生点
  - 断开时保存位置到 User.last_x/last_y
```

---

## 12. MVP 验证结果

### 自动调研 + 炼化管线（已验证）

- 测试人物：萧炎（《斗破苍穹》）
- SearXNG 6 路调研：60 条结果，32.4 秒
- MiniMax-M2.5 炼化：2903 字符输出，28.0 秒
- Token 用量：input=8718, output=2291
- 输出质量：三层结构完整，心智模型具体，表达 DNA 有辨识度，诚实边界有深度
- 结论：**管线可行**

### AI 头像生成（已验证）

- 模型：gemini-3-pro-image-preview (Vertex AI)
- 生成质量：高清 Q 版插画风，角色特征准确
- 尺寸：896×1200（需裁剪缩放为标准头像尺寸）
- 结论：**可用于头像/立绘，不可用于 32×32 精灵表**

---

## 13. 技术依赖

| 组件 | 技术 | 位置 |
|------|------|------|
| 搜索 | SearXNG | 100.93.72.102:58080 |
| LLM（炼化/对话） | MiniMax-M2.5 | DashScope Anthropic 兼容接口 |
| LLM（头像） | gemini-3-pro-image-preview | Vertex AI via new-api (100.93.72.102:3000) |
| OAuth（LinuxDo） | connect.linux.do | 环境变量：`LINUXDO_CLIENT_ID`, `LINUXDO_CLIENT_SECRET`, `LINUXDO_REDIRECT_URI` |
| 后端 | FastAPI + SQLAlchemy | Python |
| 前端 | React 18 + TypeScript + Phaser 3 | |
| 实时通信 | WebSocket | |
| 数据库 | PostgreSQL | |
