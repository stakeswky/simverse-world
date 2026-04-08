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

## 7. 数据模型变更汇总

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

---

## 8. API 变更汇总

### 新增端点

```
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
```

### 修改端点

```
WebSocket handler 扩展:
  - 新消息类型: player_chat, player_chat_reply, set_reply_mode
  - 连接时使用 User.last_x/last_y 作为出生点
  - 断开时保存位置到 User.last_x/last_y
```

---

## 9. MVP 验证结果

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

## 10. 技术依赖

| 组件 | 技术 | 位置 |
|------|------|------|
| 搜索 | SearXNG | 100.93.72.102:58080 |
| LLM（炼化/对话） | MiniMax-M2.5 | DashScope Anthropic 兼容接口 |
| LLM（头像） | gemini-3-pro-image-preview | Vertex AI via new-api (100.93.72.102:3000) |
| 后端 | FastAPI + SQLAlchemy | Python |
| 前端 | React 18 + TypeScript + Phaser 3 | |
| 实时通信 | WebSocket | |
| 数据库 | PostgreSQL | |
