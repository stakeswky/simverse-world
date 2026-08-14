# 线 A · 政治层边界 hotfix 报告

- 分支 `fix/civic-boundary-hotfix`，base `999e098`
- 4 个 commit：`0063139` → `ca2fcea` → `60403b7` → `6532372`
- **未合并、未 push、未部署**（红线）

## 结论先行

| 件 | 状态 | 关键性质 |
|---|---|---|
| 漏洞 1 · 创建路径不写 `resident_type` | 已修（5 处） | 新取值 `"resident"`，**不触碰 `!= "player"` 谓词家族** |
| 漏洞 2 · `purge_residents` 不校验类型 | 已修 | **raise 而非静默跳过**；查库而非信传入对象 |
| 边界散落 10 处 `== "npc"` | 已按语义拆成 **2 个**常量 | A 类 3 处收窄；B/C 类 7 处**必须不收窄** |
| 回归探针 | 已加（只读零 LLM） | 泄漏复发会被 🔴 点名 |

**两条必须带到收口决策的信息**：

1. **存量回填与线 B 的 P0 恢复是耦合的** —— 见 §5，位置显著。
2. **合并冲突预告与任务书给的不一致** —— 实测只有 1 个文件冲突，且不是任务书点的那个。见 §7。

---

## 1. 三件的现状证据

### 1.1 漏洞 1 — 创建路径不写 `resident_type`（5 处）

模型默认值：`backend/app/models/resident.py:52`

```python
resident_type: Mapped[str] = mapped_column(String(20), default="npc")
```

AST 扫描 `backend/app/` + `backend/seed/` 全部 `Resident(...)` 构造点，**独立复核出的漏写清单与人工清单逐行一致**（行号为 base `999e098`）：

| 路径 | file:line | 说明 |
|---|---|---|
| forge 当前主路径 | `backend/app/forge/pipeline.py:155` | **用户创角主流程** |
| legacy forge full | `backend/app/forge/legacy_pipeline.py:147` | |
| legacy forge quick | `backend/app/forge/legacy_pipeline.py:298` | `origin="quick_forge"`（见 §5 注意） |
| POST `/residents/import-card` | `backend/app/routers/residents.py:179` | |
| POST `/residents/import` | `backend/app/routers/residents.py:276` | |

显式写的 3 个，**本线未改**：

- `backend/app/services/onboarding_service.py:81` → `"player"`（全仓唯一）
- `backend/seed/preset_characters.py:1259` → `"npc"`（内置阵容，`origin="preset"`）
- `backend/app/routers/admin/residents.py:148` → 取请求参数（admin 端）

后果：玩家造的居民 `resident_type="npc"`，直接获得投票权与被选举权。07-25 审计的 14 个投票人里已实际出现「夜风侦探」×3 与「部署回归图灵0724」。

### 1.2 漏洞 2 — `purge_residents` 不校验类型

- `backend/seed/reset_builtin_residents.py:57` 的 `find_targets()` 第一个条件就是 `Resident.resident_type != "player"` → **自动路径本来是安全的**。
- 但 `purge_residents(db, targets)` 直接拿 id 列表无条件级联删十几张表（Message / Conversation / Memory / PersonalityHistory / ResidentGoal / ResidentRelation / LLMUsage / BulletinPost / Commission / Follow / FeedEvent / Debate / ResidentTreasury + null `users.player_resident_id`），**对传进来的 id 不做任何类型校验**。
- 2026-07-25 16:53 的手工阵容迁移绕过 `find_targets` 直接调 `purge_residents`，把 12 个玩家角色一起删了。这是本次修复的直接动因。
- 全仓唯一生产调用点是 `reset_builtin_residents.py` 的 `main()`（走 `find_targets`），因此加默认拒绝不影响任何现存调用（`grep -rn purge_residents --include=*.py` 实测）。

### 1.3 边界散落 10 处

全仓 `Resident.resident_type == "npc"` 共 10 处，已全部转成 `.in_(常量)`；`grep` 复核剩 0 处查询形式命中（剩的 1 条命中是 `reset_builtin_residents.py:9` 的 docstring 散文，非查询）。

---

## 2. 两个常量的 A/B 分类 —— 逐处理由

新增 `backend/app/services/civic_membership.py`：

```python
CIVIC_VOTER_TYPES  = frozenset({"npc"})               # A 类 3 处
SIM_RESIDENT_TYPES = frozenset({"npc", "resident"})   # B/C 类 7 处
UGC_RESIDENT_TYPE  = "resident"
```

### 为什么必须拆（这是本线最重要的判断）

**今天** UGC 居民恰好也是 `"npc"`，10 处等价，收敛成单常量看起来是纯重构。但 hotfix-2 一落，同一个常量在 B/C 类立刻变成回归：

- UGC 居民的值班会**静默查不到**（`duty_service.find_duty_resident` 返回 `None` → 不干活、不领薪）
- **stale mayor 标记永不清理** → 小镇同时有两个镇长，其中一个白拿工资加成
- 从 **townhall 名册消失**
- 被排除出 **burn-in 探针分母** → 世界规模被低报

这与 `!= "player"` 那个陷阱同类，只是藏在 `== "npc"` 内部。

### A 类 · 政治权利 → `CIVIC_VOTER_TYPES`（收窄的目标）

| file:line（改后） | 函数 | 理由 |
|---|---|---|
| `app/services/civic_service.py:156` | `run_npc_voting` | 真正投票那一步，主动投票权 |
| `app/services/civic_service.py:535` | `_eligible_voter_count` | 法定人数分母，必须与上一行的电子人口**严格同步**；只放宽分母会让每次投票都流会 |
| `app/services/election_service.py:43` | `open_election` | 候选池 = 被选举权；无投票权者也不应能参选 |

### B 类 · 世界人口 / 运维 sweep → `SIM_RESIDENT_TYPES`（收窄即回归）

| file:line（改后） | 语义 | 收窄后的具体故障 |
|---|---|---|
| `app/routers/townhall.py:54` | 名册投影（读/展示） | UGC 居民从市政厅名册消失 |
| `app/services/duty_service.py:109` | 值班持有者查找 | **劳动，非政治**；UGC 值班者查不到 → 静默停工停薪 |
| `app/services/office_service.py:226` | mayor meta 清理 sweep | 运维；vacate 后留下幽灵镇长 |
| `app/services/election_service.py:139` | `install_mayor` set/clear sweep | 运维；同上。**与 `:43` 语义不同，刻意用不同常量** |
| `app/services/civic_service.py:659` | 讲座辩论池 | 社交；UGC 居民被排除出小镇社交生活 |

### C 类 · 只读探针 → `SIM_RESIDENT_TYPES`（口径同 B）

| file:line（改后） | 说明 |
|---|---|
| `scripts/burnin_report.py:663` | mayor 一致性探针；UGC 身上的 stale flag 必须仍可见 |
| `scripts/burnin_report.py:813` | 工资账单探针；账单覆盖所有真持有值班的人 |

### 关键判定 1 · `"preset"` 今天没有政治权利

10 处原本全是 `== "npc"`，admin 创建的 `"preset"`（`app/schemas/admin.py:129` 默认值）从来落不进去。所以 A 类常量取 `frozenset({"npc"})` 时**是纯重构**。

> **待决项**：`"preset"` 要不要并入政治层，是独立的产品决策。**本线明确不做。** hotfix-4 的探针会把它作为「两列之外的取值」⚠️ 报出来，避免被遗忘。

### 结构守卫

`tests/test_civic_membership_boundary.py::test_no_bare_npc_comparison_remains_in_tree` 用正则 `\.resident_type\s*==\s*['"]npc['"]` 扫全树，新增裸字面量会红。只匹配带点号的查询形式，docstring 散文不算误报。

---

## 3. 5 处创建路径写 `"resident"` 的理由

### 为什么需要显式写

根因是**漏写**，不是写错。所以守卫也守漏写：`test_every_resident_construction_sets_resident_type_explicitly` 用 AST 扫 `app/` + `seed/` 全部 `Resident(...)`，任一处不带 `resident_type=` 关键字就红。新增构造点忘了写，会在这里失败，而不是一年后在选举审计里。

### 为什么不是 `"player"`（已查清，别再改回去）

1. **`users.player_resident_id` 是单值 FK**（`app/models/user.py:30`），且 `onboarding_service.py:53` 在已有时直接 `raise` → 一个 user 恰好一个化身，是硬约束。
2. 那 5 条泄漏路径**从不碰 `player_resident_id`**，只写 `creator_id=user.id` 与 `meta_json.origin ∈ {forge, quick_forge, import}` → 它们是「玩家**创作**的角色」，不是化身。测试逐条断言 `player_resident_id is None`。
3. 写 `"player"` 会踩 `!= "player"` 谓词家族并造成**三处真实回归**：
   - `app/agent/map_data.py:475` → UGC 居民从世界地图消失
   - `seed/reset_builtin_residents.py:57` → 变成 purge 候选
   - `app/routers/home_decor.py:56` → 创作者能改它的装修

### 本方案的关键性质

> 取任何 ≠`"player"` ≠`"npc"` 的值，即可**在不触碰 `!= "player"` 家族的前提下**摘掉政治权利。

`"resident"` 天然满足 `!= "player"`，所以上面那三处行为**完全不变**——这是对的，本线绝不碰那个家族。已用 `test_ugc_residents_are_not_purge_candidates` 交叉验证 `find_targets` 的答案不变。

### 关键判定 3 · 不需要迁移

`resident_type` 是裸 `String(20)`，无 enum 无 CHECK（`app/models/resident.py:52`），admin 端本来就能任意赋值（`app/routers/admin/residents.py:113`）。新增取值是**纯代码改动**。这一点很重要——红线禁止「迁移 + 行为变更」同一次落地，而 07-25 违反过的正是这条。

### a/b 必须同一提交

`ca2fcea` 里同时做了：

- (a) 5 处创建路径写 `resident_type=UGC_RESIDENT_TYPE`
- (b) `SIM_RESIDENT_TYPES` 从 `{"npc"}` 扩成 `{"npc", "resident"}`
- (c) `app/routers/admin/residents.py:40` 的 NPC/Player 标签元组加 `UGC_RESIDENT_TYPE`

a 与 b 分开提交会产生中间态：UGC 已写 `"resident"` 但人口集合还是 `{"npc"}` → §2 列的 5 条 B 类故障全部发生。

(c) 是必须一起改的副作用：`"Player"` 在 admin 面板的语义是「玩家本人的化身」，UGC 居民不是化身，标成 Player 是真实的报表 bug。

---

## 4. purge 防呆的失败语义

`backend/seed/reset_builtin_residents.py`：新增 `PlayerPurgeRefused(RuntimeError)` + `purge_residents(db, targets, *, allow_players: bool = False)`。

| 设计选择 | 理由 |
|---|---|
| **raise，不静默跳过** | 静默跳过会向「要求删掉这些 id」的调用方返回成功，调用方于是相信已经删干净了。07-25 那个脚本无论哪种语义都会「成功」，**只有 raise 才拦得住**。 |
| **查库，不信传进来的对象** | 出事的调用点是自己拼的 target 列表，所以 `target.resident_type` 恰好是唯一不能信的字段。权威校验是按 id 查库。测试用一个伪造 `resident_type="npc"` 的假对象验证拦得住。 |
| **守卫跑在第一条 DELETE 之前** | 拒绝是真正的 no-op：同批次里合法的 NPC 目标及其依赖行也一行不动。测试断言 9 张表逐表计数不变。 |
| **`allow_players` 默认 False 且 keyword-only** | 安全值必须是默认值；需要记得的 opt-out 等于没有守卫。keyword-only 让调用点自解释、可评审。 |
| **报文点名到 slug** | 07-25 的操作者没有任何办法知道自己手拼的 id 列表里哪些是玩家角色。 |

模块 docstring 的「player characters are NEVER touched」从**文档承诺**变成**代码强制**——之前这个承诺只对自动路径成立。

---

## 5. ⚠️ 存量回填口径 + 与线 B P0 恢复的耦合警告

> **这一节是交给收口时恢复决策的，不是可选阅读。**

### 耦合警告

- live 库当前用回填判别式命中 **0 行**——**原因是 07-25 那次误清把所有 UGC 居民连带删掉了**，不是本来就没有。07-25 审计里那 14 个投票人含「夜风侦探」×3 就是证据。
- **因此本线与线 B 的 P0 恢复是耦合的**：**一旦拿 07-25 备份做恢复，泄漏的存量 UGC 居民会一起被恢复回来，回填就从「不需要」变成「必须」。**
- 换句话说：**恢复动作本身会重新引入泄漏的存量数据。** 代码修好了不代表数据是干净的——恢复后必须跑回填，否则被恢复的 UGC 居民立刻重新拿到投票权与被选举权。

### 回填判别式

已在 dev 库验证 `origin` 字段每条创建路径都写：

```sql
UPDATE residents SET resident_type = 'resident'
WHERE resident_type = 'npc'
  AND creator_id != <SYSTEM_USER_ID>
  AND json_extract(meta_json, '$.origin') IN ('forge', 'quick_forge', 'import');
```

> **⚠️ 对任务书给的判别式的修正**：任务书写的是 `IN ('forge','import')`，但 `app/forge/legacy_pipeline.py:298`（legacy forge quick）写的 origin 是 **`"quick_forge"`**，不是 `"forget"`/`"forge"`。**漏掉 `'quick_forge'` 会让 legacy 快速锻造出来的 UGC 居民留在 `'npc'` 上，回填不彻底。** 上面的 SQL 已补。
>
> Postgres 上 `json_extract` 需换成 `meta_json->>'origin'`（live 库是 PG）。

内置阵容是 `origin='preset'` 且 `creator_id=SYSTEM_USER_ID`，不会被误伤（dev 库实测：14 npc/preset + 1 player/onboarding）。

### 回填的发布纪律

**回填单独一次发布，绝不与本线的代码改动同一次上线。** 这正是 07-25 违反过的红线（迁移/清库 与 行为变更 混在一次，出事既无法归因也无法单独回滚）。

### 回填与线 C 的顺序（推荐）

保守做法：回填把**所有**存量 UGC 降为 `'resident'`，再由线 C 的晋升定时任务把够门槛的重新升回 `'npc'`。

这样回填不依赖门槛设计，两条线排期解耦。**推荐这个顺序。**

---

## 6. 线 C（门槛晋升）接手说明

完整方案是「UGC 角色默认无票，满足门槛后由定时任务升为 `npc`」。**本线只做「默认无票」那一半。** 晋升逻辑（门槛条件、定时任务、状态迁移）是独立特性，不属于 hotfix，本线未做。

### 本线为线 C 保证的性质

> `SIM_RESIDENT_TYPES` 同时含 `"npc"` 与 `"resident"`，所以将来晋升**只增加政治权利、不改动世界人口归属**。

即：`"resident"` → `"npc"` 的状态迁移只需改一个字段，不需要同步任何 B/C 类查询：

- 晋升前后都在 `SIM_RESIDENT_TYPES` 里 → 名册、值班、mayor sweep、辩论池、探针分母**全部不变**
- 只有 `CIVIC_VOTER_TYPES` 的成员资格发生变化 → 只影响投票、法定人数、候选池

`CIVIC_VOTER_TYPES ⊂ SIM_RESIDENT_TYPES` 已有断言守着（`test_voters_are_a_subset_of_inhabitants`）：投票人必须先是居民，否则就是「拿着选票的幽灵」。

### 线 C 落地时的检查点

1. 晋升写的是 `resident_type = "npc"`，**不要**发明第五个取值——否则又要动 10 处谓词。
2. 晋升后 admin 标签仍是 `NPC`（`"npc"` 已在元组里），无需改 `admin/residents.py`。
3. hotfix-4 的探针会自动反映晋升效果：`resident` 一行计数下降、`npc` 一行上升，无需新探针。
4. 若线 C 选择「把 `resident` 直接并入 `CIVIC_VOTER_TYPES`」而不是逐个晋升 —— 探针会 🔴 报「UGC 取值拿到了投票权（泄漏复发）」。那是**刻意的告警**，届时需要一并调整探针的 `leaked` 判定（`scripts/burnin_report.py` 里 `if is_voter and rtype not in ("npc",)`）。

---

## 7. 合并冲突预告 —— 实测结果与任务书不一致

用 `git merge-tree --write-tree`（只读，不建 ref、不动工作树）对两个兄弟分支实测：

```
git merge-tree --write-tree --name-only HEAD feat/s1-1-reputation      → exit=1
git merge-tree --write-tree --name-only HEAD feat/s2-5-fiscal-wiring   → exit=0
```

### 实测 vs 任务书预告

| 文件 | 任务书预告 | **实测** |
|---|---|---|
| `election_service.py:40`（A 类） | **必然冲突** | ✅ **自动合并** |
| `election_service.py:133`（B 类） | 预计自动合并 | ✅ 自动合并 |
| `civic_service.py:153/527/649` | 预计自动合并 | ✅ 自动合并 |
| `duty_service.py:105` | 预计自动合并 | ✅ 自动合并（整分支 exit=0，零冲突） |
| `scripts/burnin_report.py` | **未预告** | 🔴 **唯一冲突，2 处** |

**为什么 `election_service.py:40` 没冲突**：声誉线的插入点在 `open_election` 函数体的 `candidates = candidates[:4]` **之前**（base 的 `:50`–`:63`），我改的是同一函数**顶部**的 `select(...)`（base `:40`）。两个 hunk 相隔约 10 行，超过 git 3-way 的 3 行上下文，因此干净合并。

### 唯一冲突的精确行级记录

`backend/scripts/burnin_report.py`，两处，**都是「两个探针追加在同一个插入点」的平凡冲突，解法是两边都留**：

**冲突 1** — `_run()` 的 snapshot 抓取列表（base 约 `:1185`，合并结果 `:1495`–`:1499`）

```
<<<<<<< HEAD
        boundary_snap = await fetch_civic_boundary_snapshot(session)
=======
        rep_snap = await fetch_reputation_snapshot(session)
>>>>>>> feat/s1-1-reputation
```

解为：**两行都保留**（顺序无关，均为只读抓取）。

**冲突 2** — `_run()` 的 return 拼接尾部（base 约 `:1201`，合并结果 `:1517`–`:1523`）

```
<<<<<<< HEAD
            + "\n\n" + render_probes_civic_boundary(boundary_snap))
=======
            + "\n\n" + render_probes_reputation(
                rep_snap, gate_on=settings.rep_enabled,
                min_score=settings.rep_credit_min_score))
>>>>>>> feat/s1-1-reputation
```

解为：**两段都保留**，把右括号 `)` 留在最后一段。例如：

```python
            + "\n\n" + render_probes_reputation(
                rep_snap, gate_on=settings.rep_enabled,
                min_score=settings.rep_credit_min_score)
            + "\n\n" + render_probes_civic_boundary(boundary_snap))
```

两个新探针的**函数体本身自动合并了**（都插在 `render_probes_npc_vote` 之后，但落点不同），只有 `_run` 的两处接线冲突。

### 本线在这些文件里改了哪些行（供收口对照）

改后行号（本分支 HEAD）：

```
app/services/election_service.py:26   from app.services.civic_membership import CIVIC_VOTER_TYPES, SIM_RESIDENT_TYPES
app/services/election_service.py:43   Resident.resident_type.in_(CIVIC_VOTER_TYPES)     # A 类 · open_election
app/services/election_service.py:139  Resident.resident_type.in_(SIM_RESIDENT_TYPES)    # B 类 · install_mayor
app/services/civic_service.py:29      from app.services.civic_membership import CIVIC_VOTER_TYPES, SIM_RESIDENT_TYPES
app/services/civic_service.py:156     Resident.resident_type.in_(CIVIC_VOTER_TYPES)     # A 类 · run_npc_voting
app/services/civic_service.py:535     Resident.resident_type.in_(CIVIC_VOTER_TYPES)     # A 类 · _eligible_voter_count
app/services/civic_service.py:659     Resident.resident_type.in_(SIM_RESIDENT_TYPES)    # B 类 · 讲座辩论池
app/services/duty_service.py:37       from app.services.civic_membership import SIM_RESIDENT_TYPES
app/services/duty_service.py:109      Resident.resident_type.in_(SIM_RESIDENT_TYPES)    # B 类 · find_duty_resident
app/routers/townhall.py:26            from app.services.civic_membership import SIM_RESIDENT_TYPES
app/routers/townhall.py:54            Resident.resident_type.in_(SIM_RESIDENT_TYPES)    # B 类 · _npc_residents
app/services/office_service.py:219    （函数内 import）SIM_RESIDENT_TYPES
app/services/office_service.py:226    Resident.resident_type.in_(SIM_RESIDENT_TYPES)    # B 类 · _clear_mayor_legacy_stores
scripts/burnin_report.py:663          Resident.resident_type.in_(SIM_RESIDENT_TYPES)    # C 类
scripts/burnin_report.py:813          Resident.resident_type.in_(SIM_RESIDENT_TYPES)    # C 类
app/forge/pipeline.py:163             resident_type=UGC_RESIDENT_TYPE
app/forge/legacy_pipeline.py:153      resident_type=UGC_RESIDENT_TYPE
app/forge/legacy_pipeline.py:306      resident_type=UGC_RESIDENT_TYPE
app/routers/residents.py:184          resident_type=UGC_RESIDENT_TYPE                   # import-card
app/routers/residents.py:290          resident_type=UGC_RESIDENT_TYPE                   # import
app/routers/admin/residents.py:40     ("preset", "npc", UGC_RESIDENT_TYPE)              # NPC/Player 标签
```

**⚠️ 收口注意**：`civic_service.py` 同一文件里两个常量并存是**刻意的**（`:156`/`:535` 是 A 类、`:659` 是 B 类）。`election_service.py` 同理（`:43` A 类、`:139` B 类）。**不要图省事统一。**

---

## 8. pytest 基线 vs 收工

同一条命令、同一 venv、同一 worktree（无 `.env`，走 conftest 的测试隔离分支）：

```
python3 -m pytest tests/ -q
```

### 基线（base `999e098`，动手前）

```
51 failed, 1907 passed, 25 skipped, 11 deselected, 219 warnings, 17 errors in 345.28s (0:05:45)
```

失败/错误 ID 共 **68** 条，已存档 `/tmp/civic-hotfix-base-ids.txt`。这是本机预存失败集（缺 redis / testcontainers），**硬门语义 = 相对基线零新增失败，不是 literal 0 failed**。

### 收工（HEAD `6532372`）

```
51 failed, 1952 passed, 25 skipped, 11 deselected, 223 warnings, 17 errors in 364.24s (0:06:04)
```

### 硬门判定 ✅ 通过

| 指标 | 基线 | 收工 | 差 |
|---|---|---|---|
| failed | 51 | 51 | **0** |
| errors | 17 | 17 | **0** |
| 失败/错误 ID 条数 | 68 | 68 | **0** |
| passed | 1907 | 1952 | **+45** |
| skipped | 25 | 25 | 0 |

`+45` 恰好等于本线新增的 45 条测试（§9），全部通过。

ID 逐条 diff（`comm -13` / `comm -23`）：

```
=== NEW failures (in final, not in base):
FAILED tests/test_lab_runtime_v2_store_auth.py::test_service_auth_rejects_untrusted_or_invalid_tokens[eyJ...nbf:1785038078...-token_not_yet_valid]
=== FIXED (in base, not in final):
FAILED tests/test_lab_runtime_v2_store_auth.py::test_service_auth_rejects_untrusted_or_invalid_tokens[eyJ...nbf:1785036292...-token_not_yet_valid]
```

**这不是新增失败**：同一条参数化测试，param id 里嵌了动态生成的 JWT（`nbf`/`exp` 是运行时时间戳），所以两次运行的 param id 字面量不同。把 param 部分剥掉后两份 ID 列表 `diff` **完全一致**：

```
$ for f in base final; do sed 's/\[.*\]//' /tmp/civic-hotfix-$f-ids.txt | sort > /tmp/ids-$f-noparam.txt; done
$ diff /tmp/ids-base-noparam.txt /tmp/ids-final-noparam.txt
（无输出）→ IDENTICAL — zero net new failures
```

> 这 68 条是本机预存失败集（缺 redis / testcontainers，含 `tests/integration/test_lab_*_postgres.py` 全组 error）。**相对基线零新增失败 = 硬门通过。**

### 分步验证证据（每个 commit 的 `Verified-by:` 均为实跑输出）

| commit | 验证 |
|---|---|
| `0063139` hotfix-1 | 新测 15 passed；相关 8 套 59 passed；office 2 套 29 passed；`grep` 裸字面量 0 命中 |
| `ca2fcea` hotfix-2 | RED 10 failed → GREEN 29 passed；forge/import/civic/election/townhall/duty/office/map/home_decor 18 套 **141 passed** |
| `60403b7` hotfix-3 | RED ImportError → GREEN 8 passed；preset/deploy 4 套 21 passed |
| `6532372` hotfix-4 | RED ImportError → GREEN 8 passed；`-k "burnin or civic or purge or ugc"` **98 passed**；四种形态渲染实测 |

---

## 9. 新增测试清单

| 文件 | 条数 | 覆盖 |
|---|---|---|
| `backend/tests/test_civic_membership_boundary.py` | 15 | 逐 call site 钉住结果集；A/B 分类；结构守卫 |
| `backend/tests/test_ugc_resident_no_political_rights.py` | 14 | 3 条可达创建路径功能验证 + AST 漏写守卫 + legacy 源码钉；A 类摘票 / B 类不受影响 / admin 标签 |
| `backend/tests/test_purge_residents_player_guard.py` | 8 | 拒绝语义、9 表零变化、伪造对象防御纵深、opt-in、`find_targets` 不变 |
| `backend/tests/test_burnin_report_civic_boundary.py` | 8 | 探针分组/分列/泄漏告警/fail-open/只读 |
| 合计 | **45** | |

### 测试设计上的两个刻意选择

1. **每个 type 播 2 个居民**（`PER_TYPE = 2`）：`open_election` 与辩论池都要求 ≥2 成员，播 1 个分不出「被排除」和「人数不够」。
2. **辩论池那条用 `sbti_by_type` 把内置 npc 设成 `So1=L`** 让它被池过滤掉，于是断言跟踪的是**集合内容**而不是人口规模 —— hotfix-2 一改 `SIM_RESIDENT_TYPES` 这条就会翻面。否则它会是一条永远绿的空测试。

---

## 10. 本线拒绝执行 / 修正的项

| # | 任务书原文 | 处置 | 理由 |
|---|---|---|---|
| 1 | 回填判别式 `origin IN ('forge','import')` | **修正为 `('forge','quick_forge','import')`** | `legacy_pipeline.py:298` 写的是 `origin="quick_forge"`。漏掉会让 legacy 快速锻造的 UGC 居民留在 `'npc'`，回填不彻底。 |
| 2 | 「`election_service.py:40` **必然冲突**」 | **实测不冲突，已改写为实测结论** | `git merge-tree` 实测干净合并；真正冲突的是任务书未预告的 `scripts/burnin_report.py`（2 处）。硬报「必然冲突」会让收口时找错地方。 |
| 3 | 「`onboarding_service.py:76` → `player`」 | 行号修正为 **`:81`** | 实际行号（`:76` 附近是函数其它行）。 |
| 4 | 线 C 晋升逻辑 | **未做** | 任务书明确不做；本线只做「默认无票」那一半。 |
| 5 | 存量回填 | **未执行** | 任务书明确本线不执行；口径见 §5。 |
| 6 | 合并 / push / 部署 / 新增迁移 / 碰 `!= "player"` 家族 / 碰 `_npc_choice` 打分 / 碰 `_pay_wage` 内部 | **全部未做** | 红线。 |
