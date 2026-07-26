# 人口口径决策文档 · 2026-07-26

> 对应 `docs/ROADMAP.md` 近期优先级 #4：「明确玩家角色是否参与 NPC 自治，区分『注册人口』和『自治居民』，再决定 25-40 人扩容策略」。
>
> - 性质：**纯只读调研 + 决策**。本线不改任何代码、不跑任何 LLM 调用。
> - 生产取数全部走 `BEGIN; SET TRANSACTION READ ONLY; ... COMMIT;`（vm212），无任何 UPDATE/DELETE/INSERT/DDL。
> - 代码引用基线：分支 `docs/population-scope-0726`，源自 `999e098`。
> - 取数时刻：`2026-07-26 02:04–02:14 UTC`（`ssh vm212 date -u` → `Sun Jul 26 02:04:22 UTC 2026`）。
> - 文档不含任何隐私字段（邮箱、token、IP 等一律不入）。

---

## 0. 结论先行

| # | 问题 | 结论 |
|---|---|---|
| 1 | 现在有 `is_npc` / `autonomous` 标记吗？ | **没有**。全仓 grep 只命中三处 docstring。唯一的区分信号是 `Resident.resident_type`（`npc` / `player` / `preset`）+ `creator_id`。 |
| 2 | 玩家居民现在参与自治吗？ | **社会层全参与、政治层不参与**——但这条界线不是设计声明，是 8 处独立 `where` 子句偶然形成的，且有 3 条泄漏。 |
| 3 | 最严重的泄漏 | `/residents/import-card` 与 `/residents/import` 建的玩家居民 `resident_type` 落默认值 `"npc"`，**直接获得投票权与被选举权**。 |
| 4 | 三个数字（vm212 live） | 注册用户 **45** / Resident 行 **11** / 进入自治循环 **11**。 |
| 5 | 成本会不会撞 $10 预算？ | **不会**。40 人线性外推 $1.35/日 = 13.5%；要撞 80% 熔断需要最坏观测的 5.9 倍。 |
| 6 | 形象够不够？ | 25 slot − 11 内置占用 = **14 个空闲**，够撑到 25 人；到 40 人**硬缺 15 张**。 |
| 7 | 决策 A | 分级：社会层全进、政治层不进，并把界线显式化 + 修泄漏。 |
| 8 | 决策 B | **不加新字段**，收敛到一个共享 helper + 补一条 backfill。 |
| 9 | 决策 C | 分三步 `11 → 18 → 25 → 40`，每步一个硬门槛。 |

---

## 1. 现状盘点：谁在参与自治

### 1.1 现有的区分信号（唯一真相源）

| 信号 | 定义位置 | 说明 |
|---|---|---|
| `Resident.resident_type` | `backend/app/models/resident.py:52` | `String(20)`，**默认 `"npc"`**。实际三态：`npc` / `player` / `preset`。 |
| `Resident.creator_id` | `backend/app/models/resident.py:22-26` | nullable。内置 NPC 的值是 `SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"`（`backend/seed/preset_characters.py:20,1253`）；账号注销时置 NULL（`backend/app/services/settings_service.py:179-184`）。**因此 `creator_id IS NOT NULL` 不等于「玩家创建」。** |
| `Resident.reply_mode` | `backend/app/models/resident.py:53` | 只影响 WS 对话时是否自动回复（`backend/app/routers/settings.py:293-310`），**与自治循环无关**。 |

`is_npc` / `autonomous` 字段或常量：**不存在**。验证命令与全部输出：

```
$ grep -rn "is_npc\|autonomous" backend/app backend/seed backend/alembic frontend/src \
    --include="*.py" --include="*.ts" --include="*.tsx"
backend/app/agent/tick.py:50:    """Execute one autonomous tick for a resident via plugin chain.
backend/app/agent/scheduler.py:1:"""SBTI-driven daily schedule computation for resident autonomous behavior."""
backend/app/agent/loop.py:1:"""AgentLoop: centralized background task driving all resident autonomous behavior."""
```

三条全是 docstring，零字段、零标记、零常量。

### 1.2 参与集合矩阵（逐条 file:line）

**社会层——无类型过滤，玩家居民全参与：**

| 子系统 | 入口 `file:line` | 实际过滤条件 | 玩家居民 |
|---|---|---|---|
| Agent 主循环选人 | `backend/app/agent/loop.py:133-134` | `Resident.status.not_in(["sleeping"])` | **进** |
| 单次 tick 本体 | `backend/app/agent/tick.py:44-67` | 只有日行动 cap（`_over_daily_limit`） | **进** |
| 睡眠者代谢/唤醒 | `backend/app/agent/loop.py:58-60` | `status == "sleeping"` | **进** |
| 邻居感知（基础） | `backend/app/agent/phases/perceive/basic.py:22-24` | `Resident.id != ctx.resident.id` | **进**（既被看见也可被搭话） |
| 邻居感知（社交） | `backend/app/agent/phases/perceive/social.py:24-26` | `Resident.id != ctx.resident.id` | **进** |
| 两轴关系 | `backend/app/services/relation_service.py:141,161,180` | 全走 `ResidentRelation`，由聊天写入，无类型过滤 | **进** |
| 社交圈层检测 | `backend/app/services/circle_service.py:39,107,133,142` | `select(Resident)` 全量 | **进** |
| 八卦传播 | `backend/app/services/gossip_service.py:48`（`maybe_gossip`） | 由居民-居民聊天收尾触发，自身不查 Resident | **进** |
| 热度衰减 | `backend/app/services/heat_service.py:44` | `select(Resident)` 全量 | **进** |
| 心情刷新 | `backend/app/services/mood_service.py:91,131` | 全量 / `status != "sleeping"` | **进** |
| 人群密度 | `backend/app/services/crowd_service.py:68` | `status != "sleeping"` | **进** |
| 玩家偶遇 | `backend/app/services/encounter_service.py:70-76` | `status in ("idle","walking")` + 位置盒 | **进** |
| 每日任务候选 | `backend/app/services/daily_quest_service.py:35` | `status != "sleeping"` | **进** |
| 世界事件影响面 | `backend/app/services/world_event_service.py:161` | `status != "sleeping"` | **进** |

**政治层——按 `resident_type == "npc"` 过滤，`player` 型被排除：**

| 子系统 | 入口 `file:line` | 过滤条件 |
|---|---|---|
| NPC 投票人集合 | `backend/app/services/civic_service.py:140`（`run_npc_voting`），查询在 `:152-154` | `Resident.resident_type == "npc"` |
| 法定人数分母 | `backend/app/services/civic_service.py:523-528`（`_eligible_voter_count`） | `Resident.resident_type == "npc"` |
| 选举候选池 | `backend/app/services/election_service.py:32`（`open_election`），查询在 `:39-41` | `Resident.resident_type == "npc"` |
| 装/卸镇长 | `backend/app/services/election_service.py:127`（`install_mayor`），查询在 `:132-134` | `Resident.resident_type == "npc"` |
| 公职持有者查找 | `backend/app/services/duty_service.py:77`（`find_duty_resident`），查询在 `:103-107` | `resident_type == "npc"` + `meta_json IS NOT NULL` |
| 官职卸任清理 | `backend/app/services/office_service.py:220-223` | `resident_type == "npc"` + `meta_json IS NOT NULL` |
| 市政厅面板人口 | `backend/app/routers/townhall.py:48-54`（`_npc_residents`） | `resident_type == "npc"` + `meta_json IS NOT NULL` |
| 讲座辩论选手池 | `backend/app/services/civic_service.py:638`（`maybe_spawn_lecture_debate`），查询在 `:648-650` | `Resident.resident_type == "npc"` |

**唯一一处 `!= "player"` 的反向过滤：**住房占用统计 `backend/app/agent/map_data.py:471-474`（玩家居民不占内置住宅名额）。

> **本节结论**：玩家角色**已经在参与自治的社会层**（移动、聊天、关系、圈层、八卦、热度、心情、偶遇），只被挡在政治层之外。这条界线在代码里没有任何一处集中定义或注释，是 8 个 `where` 子句碰巧一致的结果。

### 1.3 三条泄漏 / 不一致（现状的实际缺陷）

**泄漏 1 —— 玩家造的居民默认拿到选举权。**

`resident_type` 的模型默认值是 `"npc"`（`backend/app/models/resident.py:52`）。全仓只有一条创建路径显式写 `resident_type="player"`：`backend/app/services/onboarding_service.py:81`。而玩家的另外两条创建入口都**没传这个字段**：

- `backend/app/routers/residents.py:179-185`（`POST /residents/import-card`，C1 灵魂卡导入）
- `backend/app/routers/residents.py:270-286`（`POST /residents/import`，SKILL.md / zip 导入）

两处都只写 `creator_id=user.id`，`resident_type` 落默认 `"npc"` → **这些玩家居民会投票（civic_service.py:152）、会进选举候选池（election_service.py:39）、能被装成镇长（election_service.py:132）、能被查成公职持有者（duty_service.py:103）。**

实证（旧库快照，`docs/reports/ops-audit-2026-07-25B.md:207-234`）：当时 14 个 `resident_type='npc'` 的投票人里，`夜风侦探` / `夜风侦探-46ff1f` / `夜风侦探-a23160` / `部署回归图灵0724` / `夏洛克-福尔摩斯` / `阿达-洛芙莱斯` / `格蕾丝-霍珀` 等明显是用户或回归测试造出来的角色，全部在投票名单内。

滥用上限：单用户日创建 cap 是 3（`backend/app/routers/residents.py:83` `IMPORT_DAILY_CAP = 3`，检查在 `:164-168`）。45 个注册用户理论上一天可以造出 135 个合法投票人，把 11 个内置 NPC 的镇务投票和镇长选举彻底淹没。

**泄漏 2 —— 「被治理」与「有投票权」的人群不一致。**

`_eligible_voter_count`（`backend/app/services/civic_service.py:523-528`）的法定人数分母只数 `resident_type == 'npc'`，而投票通过后 `_execute_outcome`（`:557` 起）的效果（建筑落地、政策生效、镇长任命）作用于整个世界，包括 `player` 型居民。玩家角色**被治理但无票**。这是可以接受的设计取向，但目前没有任何地方把它写下来。

**泄漏 3 —— `preset` 第三态被政治层静默排除。**

管理端建的居民 `resident_type` 默认是 `"preset"`（`backend/app/schemas/admin.py:129`，创建走 `backend/app/routers/admin/residents.py:255,275`，删除限定 `:289-294`），而 admin 列表把 `preset` 和 `npc` 一起显示成 `"NPC"`（`backend/app/routers/admin/residents.py:35`）。但政治层 8 处查询全部写死 `== "npc"` → **admin 建的 preset 居民会 tick、会聊天、会进圈层，却不投票、不参选、不进市政厅面板**。意图是同类，行为是两类。

---

## 2. 三个数字

**取数方式**（vm212，只读事务）：

```
ssh vm212 "cd /opt/skills-world/deploy && docker compose exec -T db psql -U postgres -d skills_world" <<'SQL'
BEGIN;
SET TRANSACTION READ ONLY;
SELECT count(*) AS users_total FROM users;
SELECT count(*) AS residents_total FROM residents;
SELECT resident_type, count(*) FROM residents GROUP BY 1 ORDER BY 1;
SELECT count(*) AS in_tick_round FROM residents WHERE status NOT IN ('sleeping');
COMMIT;
SQL
```

原始输出（`2026-07-26 ~02:05 UTC`）：

```
 users_total
-------------
          45

 residents_total
-----------------
              11

 resident_type | count
---------------+-------
 npc           |    11

 in_tick_round
---------------
            11
```

| 口径 | 定义 | 数值 | 依据 |
|---|---|---|---|
| **注册人口** | `users` 行数 | **45** | 最早 `2026-07-07 14:14:12+00`，最晚 `2026-07-23 15:01:05+00` |
| **Resident 行数** | `residents` 行数 | **11** | 全部 `resident_type='npc'`、`creator_id = SYSTEM_USER_ID`、创建于 `2026-07-25 16:53`~`17:15` |
| **进入自治循环的居民** | `agent/loop.py:133-134` 的口径 `status NOT IN ('sleeping')` | **11** | 当前 10 `idle` + 1 `walking` |

派生数字：

```
 civic_voters(resident_type='npc') = 11
 player_type                       = 0
 user_created(creator_id <> SYSTEM_USER_ID) = 0
 users_with_player_resident_id     = 0
```

live 名册（全部 11 人，与 `backend/seed/preset_characters.py` 的新阵容一一对应）：
`lin-wanqiu / zhou-dahe / chen-tiesheng / shen-jingshu / gu-mingyuan / su-xiaoman / he-qiaoyun / zhao-qiwen / jiang-lin / a-lan / luo-xiaozhou`。

### 2.1 ⚠️ 必须如实说明的异常：live 库与 07-25 审计不是同一个库

07-25 审计（`docs/reports/ops-audit-2026-07-25B.md:192-207`）测到的是 **26 residents / 14 npc / 12 player**。今天测到的是 **11 / 11 / 0**。这不是自然演化，证据如下：

```
$ ssh vm212 "docker inspect deploy-db-1 --format '{{json .Mounts}}'"
[{"Type":"volume","Name":"deploy_pgdata","Source":"/var/lib/docker/volumes/deploy_pgdata/_data", ...}]

$ ssh vm212 "du -sh /var/lib/docker/volumes/deploy_pgdata /var/lib/docker/volumes/deploy_postgres_data"
187M    /var/lib/docker/volumes/deploy_pgdata
1.1G    /var/lib/docker/volumes/deploy_postgres_data
```

- 当前 db 容器只挂 `deploy_pgdata`（187M）；`deploy_postgres_data`（1.1G）**存在但已无容器挂载**。
- 当前库 `llm_usage` 只有 **2335** 行、最早 `2026-07-13 18:10:03+00`；审计当时是 **22393** 行、最早 `2026-07-10`（`ops-audit-2026-07-25B.md:347`）。
- 当前库 `conversations = 0`，`memories = 2835`，`resident_relations = 44`。
- 但 `users` 完整保留（45 人，`2026-07-07`~`2026-07-23`），`alembic_version = 049_add_policies`。
- `docker compose ls` 显示 vm212 上只有一个 `deploy` 项目（`/opt/skills-world/deploy/docker-compose.yml`），没有第二个在跑的世界。

**我无法在只读红线内解释这次卷切换**（读旧卷需要起容器 = 写操作，未执行）。因此：

- 「live 世界当前 0 个玩家居民」是**事实**，但**不能**当成「玩家没在用这个功能」的证据——07-25 那 12 个 `player` 型居民在当前 live 库里不存在。
- `999e098` 的 bootstrap（`seed/reset_builtin_residents.py`）**不是**原因：`find_targets`（`backend/seed/reset_builtin_residents.py:53-65`）显式排除 `resident_type == "player"`，删不掉玩家角色。
- **这是一条需要 deploy 线单独排查的事故线索**，不属于本文档结论范围。

---

## 3. 成本口径与外推

### 3.1 既有数字（不重跑任何 LLM，直接引用审计）

来源 `docs/reports/ops-audit-2026-07-25B.md`（分母 = 26 居民）：

| 项 | 数值 | 出处 |
|---|---|---|
| 全局日预算 | `$10`（`BUDGET_GLOBAL_DAILY_USD=10.0`，vm212 `.env` 实测；代码默认见 `backend/app/config.py:81`） | `:323` |
| 15 天内最高日预算占用 | **8.8%**（2026-07-24，`$0.8785 / $10`） | `:323,363` |
| `$/居民·天` 最高 | **$0.0338**（07-24，分母 26） | `:324,363,393` |
| `$/居民·天` 常见区间 | `$0.005 – $0.018` | `:324` |
| 优化后预期区间 | `$0.0264 – $0.0367` | `:387,395` |
| 熔断阈值 | 80% throttle / 95% rule_only / 100% player_only | `:388,396` |

### 3.2 live 库独立复核（本次只读查询，分母 = 11）

```
SELECT date(ts) AS d, count(*) AS calls, round(sum(cost_usd)::numeric,4) AS cost
FROM llm_usage GROUP BY 1 ORDER BY 1 DESC LIMIT 8;
```

```
     d      | calls |  cost
------------+-------+--------
 2026-07-26 |   872 | 0.1114   ← 进行中（截至 02:09 UTC）
 2026-07-25 |  1209 | 0.1441
 2026-07-24 |    81 | 0.0057
 2026-07-23 |    77 | 0.0284
```

`2026-07-25` 完整一天：`$0.1441 / 11 = $0.0131` 每居民·天，占日预算 **1.4%**。与审计的 `$0.005–0.018` 常见区间一致，可作为交叉验证。

> 注：`07-24` 及更早的极低调用量（8–81 次/天）属于 §2.1 描述的那个库，不具备与审计对比的意义，此处仅列出不解读。

### 3.3 线性外推

按最坏观测 `$0.0338/居民·天`：

| 人口 | 线性 $/日 | 占 $10 预算 | 距 80% 熔断 |
|---|---|---|---|
| 11（当前） | $0.37 | 3.7% | 21× 余量 |
| 18 | $0.61 | 6.1% | 13× |
| 25 | $0.85 | 8.5% | 9.5× |
| 26 | $0.88 | 8.8%（**实测值**） | 9.1× |
| 40 | **$1.35** | **13.5%** | 5.9× |
| 40 × 2（社交超线性罚项假设） | $2.70 | 27% | 3.0× |
| 40 × 3（悲观） | $4.06 | 41% | 2.0× |

**结论：预算不是 25→40 的约束条件。** 要在 40 人撞到 80% 熔断，需要 `$0.20/居民·天` = 最坏观测的 **5.9 倍**。

**为什么成本对人口是线性的**：每人每世界日的 LLM 行动数被 `AGENT_MAX_DAILY_ACTIONS` 硬封顶（判定在 `backend/app/agent/tick.py:33,66`；代码默认 20，见 `backend/app/config.py:184`；**vm212 `.env` 实测为 100**，与 `docs/ROADMAP.md:45` 一致）。所以总成本 ≈ 人口 × cap × 单次行动成本，人口项是一次方。

**未量化的超线性风险（标注，不外推）**：地图面积固定，人口上升会抬高相遇密度，`CHAT_RESIDENT` 在每人日行动里的占比可能上升，而一次居民-居民对话是 11–13 次调用的重头（`backend/app/agent/loop.py:243-244` 注释）。**这一项没有任何实测数据**，扩容每一步都必须先量再走（见 §5.C 门槛）。

---

## 4. 形象供给约束（对形象线 M3 最有下游价值的一节）

### 4.1 canonical 清单是什么

- 文件：`frontend/config/resident-sprite-generation.json`
- `catalog_id`: `simverse-static-sprite-slots-v1`，`schema_version: 1`
- `slots` 长度：**25**
- 清单自述（`notes[0]` 原文）：`"These entries describe 25 reusable static sprite slots, not the current database resident roster."`

⚠️ **该文件当前未被 git 跟踪**：

```
$ git ls-files --error-unmatch frontend/config/resident-sprite-generation.json
error: pathspec 'frontend/config/resident-sprite-generation.json' did not match any file(s) known to git
```

它只存在于主工作区 `/Volumes/data/dev/simverse-world/frontend/config/` 的工作树里（形象线在制品），**尚未进 master**。本文档的所有 slot 数字基于该在制品文件。

### 4.2 25 个 slot 到底对应谁

| 分类 | 数量 | sprite_key |
|---|---|---|
| **被 11 位内置 NPC 占用** | 11 | 伊莎贝拉、沃尔夫冈、约翰、简、乔治、梅、玛丽亚、亚瑟、山本百合子、海莉、拉吉夫 |
| **空闲（可用于扩容）** | 14 | 亚当、克劳斯、卡洛斯、卡门、埃迪、塔玛拉、山姆、弗朗西斯科、拉托亚、汤姆、瑞恩、詹妮弗、阿伊莎、阿比盖尔 |

内置阵容的 `sprite_key` 出处：`backend/seed/preset_characters.py:108,180,252,324,396,468,540,612,684,758,832`。11 个 key **全部**在 25-slot 清单内，零缺口。

### 4.3 已知不一致：玩家居民的随机形象池只有 20 个

玩家/导入居民的 `sprite_key` 从 `SPRITE_KEYS` 随机取（`backend/app/services/resident_placement.py:66-71`，取用在 `backend/app/routers/residents.py:182,289`）。该池只有 **20** 个 key，是 25 的真子集，缺 5 个：

```
catalog(25) - SPRITE_KEYS(20) = ['卡门', '拉吉夫', '瑞恩', '阿伊莎', '阿比盖尔']
SPRITE_KEYS - catalog = []          # 池里没有清单外的野 key
```

其中 **拉吉夫** 是内置 NPC 骆小舟正在用的形象，却不在玩家池里——说明这个池是手工维护的、已经和 catalog 漂移。另外模型默认值写死 `sprite_key = "伊莎贝拉"`（`backend/app/models/resident.py:41`），与内置 NPC 林晚秋撞形象。

### 4.4 扩容到 40 人的形象账

| 目标人口 | 需要的形象数 | 已有供给 | 缺口 |
|---|---|---|---|
| 18 | 18 | 11 占用 + 14 空闲 = 25 | 0（用掉 7 个空闲，剩 7） |
| 25 | 25 | 25 | **0（正好用满）** |
| 40 | 40 | 25 | **15** |

**前提是「一人一形象」。** 如果接受复用（现状就是复用：20 个 key 随机分给任意多居民），缺口为 0，但 40 人平均每个 sprite 被 1.6 人共用，视觉上会明显撞脸——这是产品取向问题，不是技术约束。

另需注意 `docs/ROADMAP.md:40`（近期优先级 #7）：**25 张居民纹理的来源映射与授权审计尚未完成**，release provenance gate 还没绿。在这条没绿之前新增第 26~40 张形象，等于在未结清的授权债上继续加杠杆。

---

## 5. 决策

### A. 玩家创建的居民是否进入 NPC 自治循环？

**推荐：分级——社会层全进、政治层全不进，并把这条界线从「8 处 where 巧合」升级成「一处显式定义」，同时修掉 §1.3 泄漏 1。**

具体：
- 保持现状的社会层参与（移动、聊天、关系、圈层、八卦、热度、心情、偶遇），**一行不改**。
- 政治层（投票、选举候选、镇长、公职、法定人数分母、市政厅面板、辩论选手）保持仅限系统 NPC。
- **修**：`/residents/import-card` 与 `/residents/import` 两条创建路径显式写 `resident_type="player"`。

**理由：**
1. 社会层参与是世界「活着」的来源。玩家居民出现在别人的 `perceive` 半径里（`backend/app/agent/phases/perceive/basic.py:22-24`）本身就是内容，而且**零边际成本**——它们已经在 tick 了，摘出去反而要动 `loop.py:133` 这个最热的查询。
2. 政治层是**可被刷的**。投票是纯规则、零 LLM、零随机（`civic_service._npc_choice`），一个用户日造 3 个居民（`routers/residents.py:83`），45 个注册用户一天理论上能造 135 个投票人。这不是假想——07-25 审计的 14 个投票人里已经有 3 个同名 `夜风侦探*`（`ops-audit-2026-07-25B.md:224-226`）。
3. 法定人数分母跟着投票人集合走（`civic_service.py:523-528`），玩家居民涌入会同时抬分子和分母，让 S2-5 刚做完的门槛/法定人数机制失去判别力。
4. 玩家真正的政治参与出口应该是**玩家自己的一票**（用户层），而不是「多造几个小号」。这条出口现在还没有——是后续设计题，不在本文档范围。

**反对意见（记录，不采纳）：**
- *「玩家造的角色不能参政，那玩家为什么要造角色？」* — 玩家角色仍可提案（`proposal_service` 走 `WorldChangeProposal`，与 NPC 投票是两条路）、可被内置 NPC 讨论、可进社交圈层、可参与辩论下注（`debate_service.py:5`）。参政权和存在感不是一回事。
- *「全不进更简单」* — 把玩家居民从 tick 摘出去会让它们在地图上变成雕像，且回归面（`loop.py` 主查询）比政治层 8 处 `where` 大得多。
- *「全进更公平」* — 见理由 2、3，等于把治理机制交给创建 API 的日配额。

**可逆性：高。** 政治层过滤已经全部收敛在同一个谓词上，换成共享 helper 是纯重构；创建路径补字段是一行。唯一带历史包袱的是存量数据——需要一次性 backfill（见决策 B 第 4 步），且 backfill 可反推回滚（旧值能从 `creator_id` 重新推导）。**在 live 库上这条 backfill 当前命中 0 行**（§2 已验证 `user_created = 0`），**现在做代价最低**。

---

### B. 「注册人口」与「自治居民」是否要成为显式模型概念？

**推荐：不加新字段。把语义收敛到一处共享定义（代码常量 + helper），而不是新增一列数据。**

**理由：**
1. `resident_type` **已经**承载了这个语义，问题不在表达力不足，而在三处写坏：(a) `/residents` 两条创建路径不写它；(b) 第三态 `preset` 与政治查询的 `== 'npc'` 不一致；(c) 没有任何一处集中定义「哪些 type 算自治公民」。
2. 新增 `is_autonomous` 之类的字段会立刻变成**第二个真相源**，和 `resident_type` 二次漂移——这正是 §4.3 里 `SPRITE_KEYS` 与 catalog 漂移的同一个病。
3. 加字段的代价：alembic 迁移 + 全量 backfill + schema/admin/前端暴露，改动面远大于问题本身。

**最小改动方案（本线不实现，交给后续实现线）：**

1. 在 `backend/app/services/resident_service.py` 新增一处定义：
   ```python
   # 自治公民 = 参与政治层（投票 / 选举 / 公职 / 法定人数）的居民类型。
   # 社会层（tick / 聊天 / 关系 / 圈层 / 八卦）不使用这个过滤，全体居民参与。
   CIVIC_RESIDENT_TYPES = ("npc", "preset")

   def civic_residents_stmt():
       return select(Resident).where(Resident.resident_type.in_(CIVIC_RESIDENT_TYPES))
   ```
2. 把 8 处 `Resident.resident_type == "npc"` 全换成该 helper：
   `civic_service.py:153`、`civic_service.py:527`、`civic_service.py:649`、
   `election_service.py:40`、`election_service.py:133`、
   `duty_service.py:105`、`office_service.py:222`、`routers/townhall.py:51`。
3. `backend/app/routers/residents.py` 两条创建路径（`:179-185`、`:270-286`）显式传 `resident_type="player"`。
4. 一次性 backfill 脚本（幂等、可反推）：
   ```sql
   UPDATE residents SET resident_type = 'player'
   WHERE resident_type = 'npc'
     AND creator_id IS NOT NULL
     AND creator_id <> '00000000-0000-0000-0000-000000000001';
   ```
   live 库当前命中 **0 行**（§2 已验证）。
5. 新增回归测试：断言 `POST /residents/import-card` 建出的居民**不出现在** `run_npc_voting` 的投票人集合里、**不进** `open_election` 候选池。红/绿对照必须先在旧代码上 FAIL。

**反对意见 / 未决问题：**
- **`preset` 到底算不算自治公民？** 上面第 1 步把它并入 `CIVIC_RESIDENT_TYPES` 是**推测**：`backend/app/routers/admin/residents.py:35` 把 `preset` 和 `npc` 一起显示成 `"NPC"`，说明意图是同类。但**没有任何测试或文档确认这一点**，现状代码行为是把 preset 排除在政治层外。实现线**必须先确认再合并**，不要默认合并。
- 有人会主张「注册用户数」本身应该进模型（比如 `world_stats` 表）。不推荐：这是运维口径，`SELECT count(*) FROM users` 已经够用，进模型只会多一份要同步的缓存。

**可逆性：高。** 全部是纯代码收敛加一条可反推的 backfill，无 schema 变更、无迁移。

---

### C. 25→40 扩容的分步方案

**推荐路径：`11 → 18 → 25 → 40`，四个阶段、三道门。**

| 阶段 | 目标人口 | 新增来源 | 前置门槛（**全绿**才允许进入下一步） |
|---|---|---|---|
| **C0**（先决，不加人） | 11 | — | ① 决策 A/B 的类型收敛落地，且带红/绿对照测试；② §2.1 的 pgdata 卷切换事故查清，确认没有第二个在跑的世界、也确认玩家居民不会再无声消失；③ `burnin_report.py` 增加一条只读的「人口/自治人数/类型分布」探针（零 LLM）。 |
| **C1** | **18** | 内置阵容 +7，取自 14 个空闲 slot | **成本**：连续 7 天 `$/居民·天 ≤ $0.04` 且日预算占用 ≤ 20%；**形象**：7 个新 slot 的 sprite 已生成并过 M3 QC；**性能**：tick round 耗时有实测 p95 基线（`observe_tick_round`，`backend/app/agent/loop.py:101`）。 |
| **C2** | **25** | 内置阵容 +7，用满剩余空闲 slot | **成本**：18 人下连续 7 天日预算占用 ≤ 30%；**社交**：`circle_service.refresh_circles`（`:88`）在 18 人下产出 ≥ 2 个圈层，且没有退化成单一巨型连通块；**政治**：至少 1 张新 poll 的 NPC 投票分布熵 > 0（复用 `burnin_report` 的投票分布探针，`c407832`/`3d70ed6` 已加）。 |
| **C3** | **40** | +15，**需要 25-slot 之外的全新形象** | **形象（硬门）**：`docs/ROADMAP.md:40` 的 25 张纹理来源映射与授权审计先绿，再把 catalog 扩到 40 slot 并完成同等审计；**成本**：25 人下连续 7 天日预算占用 ≤ 40%；**性能**：`agent_max_concurrent`（默认 5，`backend/app/config.py:183`）在 25 人下的一轮 tick 耗时不超过 `agent_tick_interval`（默认 60s，`:182`）——超了先调并发/间隔，再加人。 |

**理由：**
1. 每一步都刚好消耗一份**已有供给**：14 个空闲 slot 拆成两批（C1 的 7 + C2 的 7），到 25 正好用满。只有最后一步 C3 才需要新增形象产能——这样形象线可以在 C1/C2 期间**并行**准备 C3 的 15 张，而不是被扩容阻塞。
2. 每道门都对应一个**已经存在的探针**，不需要新建观测设施：成本走 `burnin_report.py --residents N`，社交走 `circle_service` 快照，政治走投票分布探针，性能走 `observe_tick_round`。
3. 18 是刻意的中间点：它让「人口从 11 涨到 25」这件事有一个可回退的观测台，而不是一步跳到 slot 上限。

**反对意见：**
- *「一步到 25，反正 slot 够」* — 25 是 slot 上限，一步跳过去就没有中间观测点；而且 8.8% 的峰值占用是在 26 人下、在一个**已经不被挂载的库**上测出来的（§2.1），不能直接当 25 人的背书。
- *「直接上 40」* — 形象缺口 15 张是硬缺口，且 40 人的社交图会不会退化成单一巨型圈层**完全没有数据**。
- *「先不扩，把政治深化（ROADMAP #5）做完」* — 有道理，但两者不冲突：C0 的类型收敛正是政治深化的前置（抽签任官、陪审都要有一个可信的「公民名册」）。

**可逆性：中。** 加居民容易，减居民会毁掉他们的记忆 / 关系 / 公职历史（删除面见 `backend/seed/reset_builtin_residents.py:8-16`：conversations、memories、personality history、goals、relations、follows/feed、debates、treasury、llm_usage、bulletin posts、commissions 全部级联删除）。因此每一步都应该**先在本地 dev 库跑满至少一个世界日**（`WORLD_CLOCK_K=4` → 6 小时真实时间）再上 vm212，且上线前先做 pgdata 卷备份。

---

## 6. 给形象线 M3 的一句话结论

> **25 个 slot 是一个可复用的静态形象库，不是人口名册**——11 位内置 NPC 各占一个（伊莎贝拉 / 沃尔夫冈 / 约翰 / 简 / 乔治 / 梅 / 玛丽亚 / 亚瑟 / 山本百合子 / 海莉 / 拉吉夫），剩下的 **14 个空闲 slot 正好覆盖到 25 人为止的全部扩容**；**扩到 40 人需要再产 15 张全新形象**，所以 **M3 本批仍按 25 slot 收口**，但请把 catalog 的命名与 `schema_version` 留出到 40 的扩展位，并顺手把 `SPRITE_KEYS`（`backend/app/services/resident_placement.py:66-71`，只有 20 个，漏了 卡门 / 拉吉夫 / 瑞恩 / 阿伊莎 / 阿比盖尔）补齐到 25、把 `frontend/config/resident-sprite-generation.json` 纳入 git 跟踪。

---

## 附录 A：取数不足 / 证据不足的地方（不外推填空）

| # | 事项 | 状态 |
|---|---|---|
| 1 | live pgdata 卷切换（26 人库 → 11 人库） | **原因未查明**。读旧卷需起容器 = 写操作，本线红线内未执行。需 deploy 线单独排查。 |
| 2 | 07-25 审计里那 12 个 `player` 型居民的去向 | **未知**。已排除 `reset_builtin_residents`（其 `find_targets` 显式排除 player）。 |
| 3 | 人口上升对 `CHAT_RESIDENT` 占比的影响（成本超线性风险） | **零实测**。§3.3 的 2×/3× 罚项是假设，不是测量。 |
| 4 | `preset` 类型是否应算自治公民 | **意图未确认**。代码行为（排除）与 admin 显示（同类）矛盾，无测试/文档定论。 |
| 5 | tick round 耗时在 >11 人下的表现 | **无基线**。`observe_tick_round` 有埋点但本线未取该指标。 |
| 6 | 玩家用户层的投票权设计 | **不存在**。当前没有「用户直接投票」的通道，决策 A 理由 4 提到的出口是未来设计题。 |
| 7 | `frontend/config/resident-sprite-generation.json` | **未进 git**，属形象线在制品，本文档的 slot 数字基于主工作区工作树快照。 |

## 附录 B：本文档用到的全部生产查询（均为只读）

```
ssh vm212 "cd /opt/skills-world/deploy && docker compose exec -T db psql -U postgres -d skills_world" <<'SQL'
BEGIN;
SET TRANSACTION READ ONLY;
SELECT count(*) AS users_total FROM users;
SELECT count(*) AS residents_total FROM residents;
SELECT resident_type, count(*) FROM residents GROUP BY 1 ORDER BY 1;
SELECT (creator_id IS NULL) AS creator_null, resident_type, count(*) FROM residents GROUP BY 1,2 ORDER BY 1,2;
SELECT status, count(*) FROM residents GROUP BY 1 ORDER BY 2 DESC;
SELECT slug, name, resident_type, creator_id, status, created_at FROM residents ORDER BY created_at;
SELECT count(*) FILTER (WHERE player_resident_id IS NOT NULL) AS users_with_player_resident, count(*) AS users FROM users;
SELECT min(created_at) AS first_user, max(created_at) AS last_user, count(*) FROM users;
SELECT version_num FROM alembic_version;
SELECT count(*) AS conversations FROM conversations;
SELECT count(*) AS memories FROM memories;
SELECT count(*) AS relations FROM resident_relations;
SELECT min(ts), max(ts), count(*) FROM llm_usage;
SELECT date(ts) AS d, count(*) AS calls, round(sum(cost_usd)::numeric,4) AS cost
  FROM llm_usage GROUP BY 1 ORDER BY 1 DESC LIMIT 8;
SELECT count(*) AS in_tick_round FROM residents WHERE status NOT IN ('sleeping');
SELECT count(*) AS civic_voters FROM residents WHERE resident_type='npc';
SELECT count(*) AS player_type FROM residents WHERE resident_type='player';
SELECT count(*) AS user_created FROM residents
  WHERE creator_id IS NOT NULL AND creator_id <> '00000000-0000-0000-0000-000000000001';
COMMIT;
SQL
```

非 SQL 的只读检查：
```
ssh vm212 "date -u"
ssh vm212 "docker compose ls"
ssh vm212 "cd /opt/skills-world/deploy && docker compose ps"
ssh vm212 "docker inspect deploy-db-1 --format '{{json .Mounts}}'"
ssh vm212 "du -sh /var/lib/docker/volumes/deploy_pgdata /var/lib/docker/volumes/deploy_postgres_data"
ssh vm212 "grep -E 'AGENT_ENABLED|BUDGET_GLOBAL_DAILY_USD|AGENT_MAX_DAILY_ACTIONS|WORLD_CLOCK_K|POLIS_|TOWN_TREASURY|REALISM_ENABLED' /opt/skills-world/deploy/.env"
ssh vm212 "cd /opt/skills-world/deploy && docker compose logs --tail 15 agent-worker"
```
