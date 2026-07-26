# 2026-07-26B 批 · P0 处置 + 政治层边界 hotfix

> 前一批（0726A）四条线已收工、全部未合并：`feat/s1-1-reputation`、`feat/s2-5-fiscal-wiring`、
> `ops/deploy-0726`、`docs/population-scope-0726`。
> 本批是**收口前的两条前置线**，决策已定：
> P0 走「先差异比对再决定恢复」、hotfix 走「泄漏 + 防呆 + 常量按语义拆分」三件一起做。

**基线仍是 `999e098`。主工作区那 76 条形象线改动全程不碰。**

---

## 0. 环境教训（上一批踩过，本批别再踩）

1. **worktree 必须在 Mac 本机建**。沙箱侧建出来的 gitdir 指针会写成 `/sessions/rcw-.../mnt/...`，
   Mac 上不存在，进去跑第一条 git 就炸。
2. **沙箱侧不要跑任何 git 写命令**。该挂载禁止 `unlink`，git 的 lock 协议半途失败，
   会在主仓库留下 `.git/index.lock`，直接挡住形象线 agent 的所有提交。
3. `/Volumes/data/dev/simverse-world-port-044` 与 `.claude/worktrees/optimistic-chebyshev-eb79f3`
   **是有效 worktree**，不是僵尸。别 prune、别删。

本批两条线的 worktree 请在你自己的终端建：

```bash
cd /Volumes/data/dev/simverse-world
git worktree add -b fix/civic-boundary-hotfix .worktrees/civic-hotfix 999e098
git worktree add -b ops/p0-roster-forensics  .worktrees/p0-forensics  999e098
```

每条线开工前的路径守卫（与上一批相同，逐字照抄）：

```bash
cd <worktree>/backend
source /Volumes/data/dev/simverse-world/backend/.venv/bin/activate
python -c "import app; p=app.__file__; assert '.worktrees/' in p, f'WRONG: {p}'; print('OK',p)"
```

**不要在 worktree 里创建 `backend/.env`**（会破坏 conftest 的测试隔离）。

---

## 1. 已定的五项决策

| # | 决策 | 落到哪条线 |
|---|---|---|
| 1 | 12 个玩家角色：**先本地起临时库做差异比对**，拿到数字再决定恢复方式 | 线 B（P0 取证） |
| 2 | 投票权泄漏：**单开 hotfix 线，泄漏 + `purge_residents` 防呆 + 常量拆分三件一起** | 线 A |
| 3 | 声誉信用闸门：**如实记为 v1 未生效**，不调参数假装工作，等 S1-2 | 收口时改 ROADMAP |
| 4 | 收口时机：**先处理 P0 和 hotfix，再按 §8 顺序合并** | 见 §4 |
| 5 | UGC 角色政治权利：**默认无票（新类型 `"resident"`），满足门槛后由定时任务升为 `npc`** | 线 A 做前半 / 线 C 做晋升 |

---

## 2. 线 A · 政治层边界 hotfix

```
任务：修掉玩家创建的居民能拿到 NPC 政治权利的漏洞，并给 purge_residents 加防呆，
同时把散在 10 处的 resident_type 谓词按语义拆成**两个**常量。三件同源，一条线做完。

工作区：
  cd /Volumes/data/dev/simverse-world/.worktrees/civic-hotfix/backend
  source /Volumes/data/dev/simverse-world/backend/.venv/bin/activate
  python -c "import app; p=app.__file__; assert '.worktrees/civic-hotfix' in p, f'WRONG: {p}'; print('OK',p)"
分支 fix/civic-boundary-hotfix，base 999e098。不要创建 backend/.env。

第 0 步：python3 -m pytest tests/ -q > /tmp/civic-hotfix-base.txt 2>&1; tail -3 /tmp/civic-hotfix-base.txt
收工同命令 diff，硬门 = 相对基线零新增失败（本机有 51 failed / 17 errors 的预存集，
不是 literal 0 failed）。

## 已核实的现状（base=999e098，逐条已复核，可直接用）

漏洞 1 — 创建路径不写 resident_type：**是 5 处，不是 2 处**（此前提示词只写了 2 处，
已更正）。全仓 `Resident(` 构造点共 8 个，落模型默认的 5 个：
- app/forge/pipeline.py:155         forge 当前主路径      ← 用户创角的**主流程**
- app/forge/legacy_pipeline.py:147  legacy forge full
- app/forge/legacy_pipeline.py:298  legacy forge quick
- app/routers/residents.py:179      POST /import-card
- app/routers/residents.py:276      POST /import
  （residents.py 全文 resident_type 零命中；:167 的日 cap 注释自己写着
   "shared with forge creations"，可见 forge 才是同一入口的主干。只堵后两条 = 漏最大的。）
显式写的 3 个（不用动）：
- app/services/onboarding_service.py:76   "player"（全仓唯一）
- seed/preset_characters.py:1259      "npc"（内置阵容，origin="preset"）
- app/routers/admin/residents.py:148      取请求参数（admin 端）

模型默认值：app/models/resident.py:52
  resident_type: Mapped[str] = mapped_column(String(20), default="npc")
后果：玩家造的居民 resident_type="npc"，直接获得投票权与被选举权。
  07-25 审计的 14 个投票人里已实际出现「夜风侦探」×3 与「部署回归图灵0724」。

漏洞 2 — purge_residents 不校验类型：
- seed/reset_builtin_residents.py:53-65 find_targets() 第一个条件就是
  Resident.resident_type != "player"，**自动路径是安全的**。
- 但 :68 purge_residents(db, targets) 直接拿 id 列表无条件级联删 8 张表
  （Message/Conversation/Memory/PersonalityHistory/ResidentGoal/ResidentRelation/
  LLMUsage/BulletinPost/Commission），**对传进来的 id 不做任何类型校验**。
- 2026-07-25 16:53 的手工阵容迁移就是绕过 find_targets 直接调 purge_residents，
  把 12 个玩家角色当成「测试角色」一起删了。这是本次修复的直接动因。

边界散落 — 10 处 `== "npc"`（行号已复核）。**逐处读过上下文后确认它们不是同一个
语义家族**，此前提示词把 8 处当成一族要收敛成单个常量，是错的：

A 类 · 政治权利（3 处，就是要收窄的目标）：
  civic_service.py:153     NPC 投票（真正投票的那一步）
  civic_service.py:527     _eligible_voter_count —— 法定人数分母
  election_service.py:40   open_election 候选池

B 类 · 世界人口 / 运维 sweep（5 处，**收窄就是回归**）：
  routers/townhall.py:51      _npc_residents —— townhall 名册投影（读/展示）
  duty_service.py:105         值班持有者查找 —— 劳动，非政治
  office_service.py:222       mayor meta 清理 sweep —— 运维
  election_service.py:133     install_mayor 的 set/clear sweep —— 运维
  civic_service.py:649        讲座辩论池 —— 社交

C 类 · 探针（2 处，口径同 B）：
  scripts/burnin_report.py:657 / :804

为什么必须拆：**今天** UGC 居民就是 "npc"，10 处等价，收敛成单常量是纯重构；但
hotfix-2 一落，同一个常量在 B/C 类立刻变成回归 —— UGC 居民的值班会静默查不到
（duty_service 返回 None）、stale mayor 标记永不清理、从 townhall 名册消失、
被排除出 burn-in 探针分母。这与 != "player" 那个陷阱同类，只是藏在 == "npc" 内部。

## resident_type 的取值语义（已查清 + Jimmy 已拍板，照此实现，不要自己发挥）

- "npc"      内置自治居民，有政治权利（seed/preset_characters.py:1259，origin="preset"）
- "player"   玩家本人的化身（onboarding_service.py:76，全仓唯一）
- "preset"   **管理端创建**的居民（schemas/admin.py:129 默认值，
             routers/admin/residents.py:294 有 != "preset" 的门）
- "resident" ← **本线新增**：玩家用 forge/import 创作的居民。**Jimmy 已定此值。**

关键判定 1 · preset 今天没有政治权利（10 处全是 == "npc"，preset 落不进去）。
所以 A 类常量取 frozenset({"npc"}) 时是纯重构。preset 要不要并入政治层是独立的
产品决策，**本线明确不做，在报告里登记为待决**。

关键判定 2 · 新值**为什么不是 "player"**（这条以前留给你问，现在已经查清，别再改）：
- users.player_resident_id 是**单值** FK（models/user.py:30），且
  onboarding_service.py:53 在已有时直接 raise → 一个 user 恰好一个化身，硬约束。
- 那 5 条泄漏路径**从不碰 player_resident_id**，只写 creator_id=user.id 与
  meta_json.origin ∈ {forge, import} → 它们是「玩家创作的角色」，不是化身。
- 写 "player" 会踩你不许碰的 != "player" 谓词家族并造成三处真实回归：
  agent/map_data.py:475 → UGC 居民从世界地图消失；
  reset_builtin_residents.py:57 → 变成 purge 候选；
  routers/home_decor.py:56 → 创作者能改它的装修。
- 取任何 ≠"player" ≠"npc" 的值，即可**在不触碰 != "player" 家族的前提下**摘掉政治权利。
  这是本方案的关键性质。

关键判定 3 · **不需要迁移**。resident_type 是裸 String(20)，无 enum 无 CHECK，
admin 端本来就能任意赋值（routers/admin/residents.py:113）。新增取值是纯代码改动。
（这一点很重要——红线禁止「迁移 + 行为变更」同一次落地。）

必须一起改的副作用（漏了就是 admin UI 显示错）：
  routers/admin/residents.py:35 硬编码 `in ("preset","npc")` → 标 NPC，否则标 Player。
  "resident" 要加进这个元组，否则 UGC 居民在 admin 列表里会显示成 Player。

另注意仓库里存在**第二个**谓词家族（世界存在感，不是政治权利）：
  reset_builtin_residents.py:57 / agent/map_data.py:475 / home_decor.py:56 用 != "player"。
**本线绝不碰 != "player" 家族**——新值天然满足 != "player"，这三处行为不变，这是对的。

## 明确不做（登记为线 C，别顺手做了）

Jimmy 拍板的完整方案是「UGC 角色默认无票，满足门槛后由定时任务升为 npc」。
**本线只做「默认无票」那一半**，晋升逻辑（门槛条件、定时任务、状态迁移）是独立特性，
需要单独走 brainstorming + plan，**不属于 hotfix**。你只要保证一个性质：
SIM_RESIDENT_TYPES 同时含 npc 与 resident，所以将来晋升只增加政治权利、
不改动世界人口归属。在报告里把这个性质写清楚，供线 C 接手。

## 任务切分（TDD，一任务一提交）

1. hotfix-1: 两个常量 + helper（**纯重构，零行为变化**）
   新建 app/services/civic_membership.py（或你判断的不制造循环 import 的位置）：
     CIVIC_VOTER_TYPES  = frozenset({"npc"})          # A 类 3 处
     SIM_RESIDENT_TYPES = frozenset({"npc"})          # B/C 类 7 处 —— 本步先只放 npc
   A 类 3 处用 CIVIC_VOTER_TYPES，B/C 类 7 处用 SIM_RESIDENT_TYPES。
   查询写法从 `== "npc"` 改成 `.in_(CONST)`。
   **先写一个断言「改动前后同一份 fixture 的查询结果集逐字节相同」的测试**，再动查询。
   10 处全改完这条测试必须绿。此步两个常量取值相同，所以确实零行为变化。
2. hotfix-2: 堵创建路径泄漏（**唯一带行为变更的一步**）
   a) 5 处创建路径显式写 resident_type="resident"（清单见上，含 forge 三处）。
   b) 同一提交里把 SIM_RESIDENT_TYPES 改成 frozenset({"npc", "resident"})。
      —— a 和 b 必须同一提交，否则中间态会让 UGC 居民从世界人口里消失。
   c) routers/admin/residents.py:35 的元组加 "resident"。
   测试三条，都要有：
   - 经这 5 条路径创建的居民**不出现在 A 类 3 处**查询结果里（政治权利被摘掉）
   - 但**仍出现在 B 类 5 处**查询结果里（世界人口、值班、名册不受影响）
   - admin 列表里它的 type 标签是 NPC 而不是 Player
3. hotfix-3: purge_residents 防呆
   给 purge_residents 加类型校验：传入含 resident_type == "player" 的目标时
   raise（而不是静默跳过——静默会让调用方以为删干净了）。
   加一个显式的 allow_players=False 参数留给真需要删玩家的场景，默认 False。
   测试：混入一个 player 的目标列表 → raise 且**一行都没删**（事务未提交，断言其他表零变化）。
4. hotfix-4:（可选）回归探针
   在 burnin_report.py 加一个只读探针：按 resident_type 分组统计
   「总数 / 进入 CIVIC_VOTER_TYPES 的数 / 进入 SIM_RESIDENT_TYPES 的数」，
   让这类泄漏下次能被自动发现。零 LLM。

## 门控与红线

- 本线**没有新开关**（是修漏洞，不是加功能），也**不新增迁移**（理由见「关键判定 3」）。
- 存量回填 —— 口径已查清，**本线不执行，但必须写进报告**：
  · live 库当前命中 0 行（人口线实测）——原因是 07-25 那次误清把所有 UGC 居民
    连带删掉了，不是本来就没有。07-25 审计里那 14 个投票人含「夜风侦探」×3 就是证据。
  · **因此本线与线 B 的 P0 恢复是耦合的**：一旦拿 07-25 备份做恢复，
    泄漏的存量 UGC 居民会**一起被恢复回来**，回填就从「不需要」变成「必须」。
    这条必须显著地写进报告，交给收口时的恢复决策。
  · 回填判别式（已在 dev 库验证 origin 字段每条创建路径都写）：
      resident_type = 'npc' AND creator_id != SYSTEM_USER_ID
      AND json_extract(meta_json,'$.origin') IN ('forge','import')
    → UPDATE 成 'resident'。内置阵容是 origin='preset' 且 creator_id=SYSTEM_USER_ID，
      不会被误伤（dev 库实测：14 npc/preset + 1 player/onboarding）。
  · 回填**单独一次发布**，绝不与本线的代码改动同一次上线 —— 这正是 07-25 违反过的红线
    （迁移/清库 与 行为变更 混在一次，出事既无法归因也无法单独回滚）。
  · 回填与线 C 的关系：保守做法是回填把**所有**存量 UGC 降为 'resident'，
    再由线 C 的晋升定时任务把够门槛的重新升回 'npc'。这样回填不依赖门槛设计，
    两条线的排期解耦。在报告里推荐这个顺序。
- 红线：不合并不 push 不部署；不碰 != "player" 谓词家族；
  不碰 _npc_choice / _npc_choice_legacy 的打分逻辑（那是声誉线的地盘）；
  不碰 duty_service._pay_wage 内部（那是财政线的地盘，你只改 :105 的查询谓词）；
  不新增迁移；不提交 backend/skills_world_dev.db；
  不在主工作区 /Volumes/data/dev/simverse-world 执行任何 git 写操作。

## ⚠️ 合并冲突预告（必须写进你的报告）

- election_service.py:40 的 == "npc"（A 类，改成 CIVIC_VOTER_TYPES）**就在 open_election
  函数体内**，而 feat/s1-1-reputation 的候选排序改的正是这个函数 → **必然冲突**。
  你不需要解决它（本线先合），但要在报告里精确记下你改了哪一行、改成什么，
  供收口时对着解。
- election_service.py:133 在 install_mayor（B 类，改成 SIM_RESIDENT_TYPES），与声誉线
  不同函数，预计可自动合并——但**别把它和 :40 用同一个常量**，两者语义不同。
- civic_service.py:153/:527/:649 与声誉线的 _npc_choice(:280) 在不同函数，预计可自动合并。
  注意 :153/:527 是 A 类、:649 是 B 类，同一文件里用两个不同常量，别图省事统一。
- duty_service.py:105 与财政线的 _pay_wage(:147) 在不同函数，预计可自动合并。

产出：docs/reports/fix-civic-boundary-hotfix-report.md——三件的现状证据（file:line）、
两个常量的 A/B 分类逐处理由、5 处创建路径写 "resident" 的理由与「为什么不是 player」、
purge 防呆的失败语义、**存量回填口径 + 与线 B P0 恢复的耦合警告**、
线 C（门槛晋升）的接手说明、以及上面四条冲突预告的精确行级记录。
```

---

## 3. 线 B · P0 取证与恢复方案（不执行恢复）

```
任务：用事故前备份在**本地**起临时库，与 vm212 live 库做差异比对，产出一份让项目所有者
能拍板的恢复方案。**本线不执行任何恢复性写操作。**

背景（已查明，不必重查）：
- 2026-07-25 16:53:47 UTC，一次手工阵容迁移绕过 reset_builtin_residents.find_targets()
  直接调 purge_residents()，把 12 个玩家角色连同 21 条「测试角色」一起级联删除。
  find_targets 本身是安全的（:57 排除 player），肇事的是绕过它的手工调用。
  **容器重启不会重演此事**——部署线之前的担心可以解除。
- 事故前完好备份：vm212 上 /opt/skills-world/deploy/db-backup-roster-20260725-164629.sql.gz（72MB）
- 那个 1.1G 的 deploy_postgres_data 卷**与本事故无关**——是 sub2api 的 PG18 集群，
  compose project 名撞车而已。别再往那个方向查。

工作区：
  cd /Volumes/data/dev/simverse-world/.worktrees/p0-forensics
分支 ops/p0-roster-forensics，base 999e098。本线只写报告，不改代码。

## 做什么

1. 把备份拉到本地，起一个**临时** PG16 容器（独立 project 名与端口，
   绝不复用 deploy 那套 compose，绝不碰 vm212 的任何卷），restore 进去。
   容器名/端口/卷名全部写进报告，收工后自己清理并在报告里确认已清理。
2. 三向差异比对，全部只读：
   a. 备份库 vs live 库：12 个玩家角色各自的完整画像——
      slug / name / creator_id / 关联 users 行 / memories 条数 / conversations 条数 /
      created_at / 最后活跃时间。**不抄邮箱等隐私字段**，用 user id 前 8 位代替。
   b. live 库这 9.5 小时（16:53:47 之后）产生了什么真实数据？
      按表统计新增行数，重点区分「系统自动产生」（agent tick / llm_usage / memories）
      与「真实用户产出」（conversations / messages / 玩家发起的动作）。
      **这是决定能不能全量回滚的唯一依据。**
   c. 那 12 个用户在事故后有没有再登录/活动？（users 表的活跃字段 + 任何带 user_id 的新行）
      如果他们已经流失，恢复的价值判断不一样。
3. 给出三个方案的可行性与代价，每个都要有具体数字，不要定性描述：
   - 方案 1 全量回滚到 16:46 快照：丢失 9.5h 的哪些具体数据（逐表行数）
   - 方案 2 只抽 12 行 resident + users.player_resident_id 回填：
     技术可行性（FK 依赖、id 冲突、alembic 版本差异 047→049 会不会让老行插不进新 schema）、
     角色回来但记忆/对话丢失对玩家意味着什么
   - 方案 3 不恢复：需要通知这 12 个用户吗
4. 明确推荐一个，并写清推荐的理由和你最不确定的地方。

## 红线

- **对 vm212 严格只读**：禁 UPDATE/DELETE/INSERT/DDL、禁 alembic、禁改 .env、
  禁 docker compose up/down/restart/build、禁重启容器、禁碰任何卷。
  psql 一律显式只读事务（BEGIN; SET TRANSACTION READ ONLY; ... COMMIT;）。
- 本地临时库随便读写，但**绝不把本地库的任何东西写回 vm212**。
- 隐私：邮箱、密码哈希、任何 PII 不得进报告。user id 一律截断。
- 备份文件只读不改，不覆盖、不移动、不删除。

产出：docs/reports/ops-p0-roster-forensics-report.md——临时库搭建与清理证据、
三向差异的具体数字表、12 个角色的画像清单（脱敏）、三个方案的代价对比、
明确推荐 + 不确定点、以及「若选方案 2，精确的 SQL 与执行前检查清单」（写出来但不执行）。
```

---

## 4. 更新后的收口顺序

```
1. fix/civic-boundary-hotfix        ← 先合。它改 8 处查询谓词，是其他线的地基
2. docs/population-scope-0726       ← 零代码
3. ops/deploy-0726                  ← 只动 .env.example
4. feat/s2-5-fiscal-wiring          ← duty_service:105 已被 hotfix 改过，:147 无交集，预计干净
5. feat/s1-1-reputation             ← ⚠️ election_service open_election 与 hotfix:40 必然冲突，
                                       对着两边报告的行级记录手工解
6. P0 恢复动作                       ← 等线 B 的数字出来、你拍板后单独执行
7. feat/resident-sprites            ← 形象线单独收口
```

收口硬门：`alembic heads` 单头（应仍是 049，本批与上批都零迁移）+ 统一补
`config.py` / `.env.example`（声誉的 `REP_*`、部署线的 `LOOP_HEARTBEAT_*` / `SOCIAL_STATUS_*`）
+ 全量 pytest 一次 + 更新 `docs/ROADMAP.md`。

**ROADMAP 要如实写进去的两条**（决策 3 的落地）：
- 声誉信用闸门 v1 **有原语无效果**：`REP_CREDIT_MIN_SCORE=-0.3` 在当前信号强度下不可达
  （纯八卦稳态下界 ≈ −0.175，探针实测最低 −0.17，拒绝面 0/13）。
  需 S1-2 越轨-制裁链补上更强负向信号后才生效。**不要在文档里表述成「已实现赊账管控」。**
- 声誉机制存在方向缺口：语气基线为负 ⇒ 没人议论的 `score=0` 反而最高，
  「好名声」无正向来源，探针偏度 −1.456（与规格预期的右偏相反）。这是设计缺口不是 bug。

---

## 5. 本批不做但已登记的隐患

| 隐患 | 证据 | 处置 |
|---|---|---|
| `deploy.sh` 的 `rsync --delete` exclude 漏了 `.env` 和 `static/portraits/` | 部署线 dry-run 实测会 `deleting .env` | 下次部署前必修，**否则谁跑一次就中招** |
| `frontend/config/resident-sprite-generation.json` 未被 git 跟踪 | 只存在于主工作区工作树 | 形象线 commit 时必须显式 `git add` 它 |
| 形象线 76 条改动仍未进分支 | 无 base、无 diff、无法 review | 尽快 commit 到 `feat/resident-sprites`（显式列路径，**不带** `skills_world_dev.db`） |
| `SPRITE_KEYS` 只有 20 个，漏 5 人 | `resident_placement.py:66-71`，漏卡门/拉吉夫/瑞恩/阿伊莎/阿比盖尔 | 形象线 M3 收口时补 |
| 四级审批路由真实行为**零验证** | 三个 poll 要到 07-27 23:29 UTC 才开票 | `POLIS_POLICY_APPROVAL_ENABLED=true` 最大的未验证面，下轮复采 |
| socializing 回收 R4 **零样本** | 部署线观察窗内未触发 | 无法证明真实卡死能被回收，需构造验证或继续等 |
| 07-25 那次「迁移 + 开闸同一次变更」已违反红线 | 三个开关 07-25 15:31 与迁移同批写入 | 流程问题，下次部署必须分两步 |

---

## 6. 仍然只有你能解的一件事

形象线的 Images API **403**：`.env` 中转认证正常、`/models` 能列出 `gpt-image-2`，
但 generations/edits 全返 403，签不出 capability receipt。
M1 的双候选盲评与 M3 的 275 次批次都开不了。需要为该账户开通 Images API 权限，或更换端点。
这条从上一批挂到现在，是整个项目当前最大的单点阻塞。
