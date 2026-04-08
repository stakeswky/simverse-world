# Minimap — 街区导航与居民传送

## 概述

在游戏界面左上角添加常驻小地图，显示 4 个街区分区和玩家实时位置。点击街区展开居民列表，点击居民执行淡入淡出传送，到达目标居民身旁。

## 需求背景

当前 140×100 格（4480×3200px）的地图过大，居民分散在 4 个街区，玩家难以找到目标居民。现有搜索框可以定位居民，但缺乏全局地图概览和街区导航能力。

## 技术方案

**Canvas 缩略图 + React 浮层**：用 Phaser RenderTexture 生成地图缩略图作为底图，街区分区和居民列表用 React 组件叠加实现，通过 PhaserBridge 事件通信触发传送。

选择理由：
- 缩略图是地图真实缩影，直观
- 玩家位置实时跟踪
- 街区交互（列表、滚动）用 React 处理最自然
- RenderTexture 一次生成并缓存，性能开销可控

## 小地图布局

- **尺寸**：180 × 130px
- **位置**：左上角，TopNav 下方（top: 52px, left: 12px）
- **底图**：Phaser RenderTexture 从 tilemap 一次性生成缩略纹理，缓存为静态图像
- **街区色块**：4 个半透明色块叠加在缩略图上
  - engineering：蓝色 `rgba(59,130,246,0.35)`
  - product：紫色 `rgba(168,85,247,0.35)`
  - academy：绿色 `rgba(34,197,94,0.35)`
  - free：黄色 `rgba(251,191,36,0.35)`
- **玩家标记**：白色圆点 + 蓝色边框，每帧更新位置
- **视野框**：白色半透明矩形，表示当前摄像机可见范围
- **样式**：深色半透明背景 `rgba(0,0,0,0.7)`，圆角 8px，细边框 + 阴影

## 街区居民列表面板

### 触发方式

点击小地图上的街区色块。

### 交互行为

1. 点击街区 → 该街区高亮（边框加粗、亮度提升、外发光），其他街区变暗
2. 小地图右侧展开居民列表面板（动画展开）
3. 再次点击同一街区 → 收起面板（toggle）
4. 点击 ✕ 或面板外区域 → 关闭面板，街区恢复正常

### 面板内容

- **头部**：街区图标 + 街区名称 + 关闭按钮
- **居民列表**（可滚动，max-height: 200px）：
  - 每行：头像圆形 28px + 名字 + 角色描述 + 状态圆点
  - 状态圆点颜色：绿色=idle/popular（可对话），灰色=sleeping/chatting（不可对话）
  - sleeping 居民行降低透明度至 0.5
  - hover 高亮行背景
- **底部提示**："点击居民传送到其身边"

### 数据来源

从 `GET /residents` 接口获取（GameScene 初始化时已缓存在内存中），按 `district` 字段分组。

## 传送效果

### 动画时序（总时长约 800ms）

| 阶段 | 时长 | 动作 |
|------|------|------|
| Phase 1: 淡出 | 300ms | 摄像机叠加黑色遮罩，alpha 从 0 → 1，Ease.QuadIn |
| Phase 2: 瞬移 | 0ms | 设置玩家位置到目标 tile，摄像机跳转跟随 |
| Phase 3: 淡入 | 500ms | 遮罩 alpha 从 1 → 0，Ease.QuadOut |

非对称节奏：淡出快（300ms）+ 淡入慢（500ms），离开感快速果断，到达感舒展自然。

### 传送期间

- 禁用玩家移动输入
- 禁用 NPC 交互
- 传送完成后恢复所有输入

### 传送完成后

- 触发 `teleport:complete` 事件
- 如果目标居民状态为 idle/popular，自动触发 `npc:nearby` 使其高亮

## 技术架构

### React 组件

```
MinimapOverlay          — 定位容器（fixed，左上角）
├── MinimapCanvas       — canvas 元素，绘制缩略纹理 + 玩家点 + 视野框
├── DistrictZones       — 4 个街区点击热区（absolute 定位在 canvas 上）
└── ResidentPanel       — 居民列表浮层（条件渲染）
```

### Phaser 侧新增

- `generateMinimapTexture()`：场景加载完成后，用 RenderTexture 渲染所有地面层到一张缩小的纹理，导出为 base64 传给 React
- `teleportTo(tileX, tileY)`：执行淡出→瞬移→淡入动画序列
- `update()` 中广播玩家 tile 坐标（复用现有逻辑，增加 bridge 事件）

### PhaserBridge 新增事件

| 事件 | 方向 | 数据 | 用途 |
|------|------|------|------|
| `minimap:texture` | Phaser → React | `{ dataUrl: string }` | 传递缩略图 base64 |
| `minimap:teleport` | React → Phaser | `{ tileX, tileY, residentSlug }` | 触发传送 |
| `teleport:complete` | Phaser → React | `{ tileX, tileY }` | 传送完成通知 |
| `player:position` | Phaser → React | `{ tileX, tileY }` | 每帧玩家位置更新 |
| `camera:viewport` | Phaser → React | `{ x, y, w, h }` | 视野框范围（tile 坐标） |

### 街区坐标映射

从 `DISTRICT_TILE_SLOTS`（forge_service.py）提取街区边界，前端硬编码映射表：

| 街区 | tile 范围（近似） | 小地图像素区域 |
|------|------------------|---------------|
| engineering | (56-64, 55-63) | 按比例换算 |
| product | (35-39, 40-52) | 按比例换算 |
| academy | (30-34, 65-77) | 按比例换算 |
| free | (100-108, 38-44) | 按比例换算 |

换算公式：`minimapX = (tileX / 140) * 180`，`minimapY = (tileY / 100) * 130`

## 与现有功能的关系

- **SearchDropdown**：保留不变，搜索框和小地图是互补功能（搜索按名字，小地图按位置）
- **camera:pan**：传送功能不复用现有 `camera:pan`（它是平滑移动），改用新的 `teleportTo` 实现淡入淡出效果
- **NpcTooltip**：传送到达后，玩家在目标居民附近，NpcTooltip 自然触发显示
- **WebSocket sendPosition**：传送后玩家位置变化会通过现有 WS 广播给其他在线玩家

## 边界情况

- **居民列表为空的街区**：显示空状态文案"该街区暂无居民"
- **地图尺寸变化**：缩略图在 `scene:ready` 时生成，如果 tilemap 变化需重新生成
- **窗口缩放**：小地图固定尺寸 180×130，不随窗口缩放
- **传送目标被占**：玩家传送到目标居民相邻 tile（偏移 1 格），避免重叠
- **连续快速点击**：传送动画期间忽略新的传送请求（锁定状态）
