# 功能开发并行开工清单（2026-07-26 · 形象生成测试期并行版）

> **前提与本批的特殊之处**：居民原创形象线（M1/M2/M3）的改动**全部未提交**，压在
> `master` 主工作区里（`git status --porcelain` = 76 条，34 个文件 +900/-200，含**未提交的迁移 050**
> 与 12 个新服务文件）。另有一个 agent 正在该工作区测试该功能。
> **本批四条线全部从 `999e098` 拉独立 worktree，看不到形象线的任何代码——这是刻意的隔离。**
> 代价：形象线将来落地时要自己承担与本批的合并冲突（见文末「形象线的悬空问题」）。

基线 commit：`999e098 fix(deploy): 内置居民阵容随部署自动同步——compose 加一次性 bootstrap`

---

## 0. worktree 已建好，直接进目录开工

| 线 | 分支 | worktree 路径 |
|---|---|---|
| 1 | `feat/s1-1-reputation` | `.worktrees/s1-1-reputation/` |
| 2 | `feat/s2-5-fiscal-wiring` | `.worktrees/s2-5-fiscal/` |
| 3 | `ops/deploy-0726` | `.worktrees/deploy-0726/` |
| 4 | `docs/population-scope-0726` | `.worktrees/population/` |

`.worktrees/` 已在 `.gitignore:8`，**不会出现在形象线 agent 的 `git status` 里**，也不会被
`git add -A` 扫进去。

### 0.1 Python 环境：复用主 `.venv`，但必须 cd 进自己的 worktree

`backend/.venv` 是 uv 建的 macOS venv，`_editable_impl_skills_world_backend.pth` 内容是一行裸路径
`/Volumes/data/dev/simverse-world/backend`（**追加**到 sys.path，不是 finder）。
`python -m pytest` 会把 CWD 放进 `sys.path[0]`，所以**只要 cd 进自己 worktree 的 `backend/`，
本地 `app` 就会遮蔽主树的 `app`**。已实测确认。

**每条代码线的第一条命令，逐字照抄（这是硬守卫，跑错路径会静默用到主树代码）：**

```bash
cd <worktree>/backend
source /Volumes/data/dev/simverse-world/backend/.venv/bin/activate
python -c "import app,sys; p=app.__file__; assert '.worktrees/' in p, f'WRONG APP PATH: {p}'; print('OK', p)"
```

断言不过就停下来查，别继续。

### 0.2 测试隔离是天然成立的，但有一个前提

`tests/conftest.py:15-22`：**只有 `backend/.env` 不存在时**才注入隔离配置
（per-PID 临时 sqlite + dummy LLM key）；有 `.env` 时 `DATABASE_URL` 默认
`postgresql+asyncpg://…@localhost:5432/skills_world`，`test_rate_limit` 的 ws chat 路径直连全局
engine → 多条线会打同一个真实 Postgres 库。

`.env` 被 `.gitignore:2` 忽略，所以新 worktree 天然没有。
**纪律：任何情况下都不要把 `backend/.env` 复制进 worktree。**
（每个测试自身用 in-memory sqlite + fakeredis，`conftest.py:28,63-77`，本来就互不干扰。）

### 0.3 开工第 0 步：存基线

```bash
cd <worktree>/backend && python3 -m pytest tests/ -q > /tmp/<线名>-base.txt 2>&1; tail -3 /tmp/<线名>-base.txt
```

收工用**同一条命令**再跑一次并 diff。
硬门 = **相对基线零新增失败**（本机含 lab-v2 需真 redis/testcontainers 的预存失败集，
不是 literal `0 failed`）。

---

## 1. 共同纪律

1. **base 一律 = `999e098`**，一任务一提交带任务号，TDD，串行门不跳步。
2. **迁移号**：本批**没有一条线需要新迁移**（见各线说明）。
   若中途发现必须加，用 `NNN` 占位、`down_revision` 接 `049_add_policies`，报告登记，
   收口统一线性化 + `alembic heads` 单头校验。
   **绝不写 `050`/`051`——`050_add_resident_sprites` 已被形象线占用但尚未提交。**
3. **`config.py` 只在 `Settings` 类尾追加自己前缀的块，不改他人行。**
   形象线的 `resident_sprite_*` 块在**中段**（`static_dir` 之后，`config.py:147+`），
   与尾部追加天然不撞。线 1 用 `rep_`/`REP_`。
4. **`nightly_cron.py` 只新增自己的独立 `try/except` 块，不改不挪既有块、不碰调度骨架。**
   骨架已被工程健康批（R3 补跑）改过，现有 `run_nightly_jobs(*, once_per_day=False)` 与
   `_claim_run_date` / `_needs_catch_up` / `_anchor_*` 一组守卫，**任何线都不许再动它**。
5. **`git add` 一律显式列路径。禁 `git add -A` / `git add .` / `git commit -a`。**
   `backend/skills_world_dev.db` 是被 git 跟踪的二进制（每个 worktree 各有一份 1.4MB 副本，
   跑测试就漂移），本批**一律不提交它**。
6. 时间语义一律走 `backend/app/world_clock.py`；预算 / TTL / 日志 / 运维 cron 用真实时间。
7. 新机制独立 bool 开关默认 `False`；规则做骨架、LLM 做血肉，**零新增 LLM 边际成本**。
8. 各线进展写 `docs/reports/<分支名>-report.md`。**不碰 `docs/ROADMAP.md`**——收口时主会话统一更新一次。
9. **红线：不合并、不 push、不在主工作区执行任何 git 写操作。**
   主工作区 `/Volumes/data/dev/simverse-world` 是形象线 agent 的独占地盘，
   在那里跑 `git checkout` / `git stash` / `git clean -fdx` / `git add -A` 会毁掉 900 行未提交工作。

---

## 2. 文件集冲突核验

### 2.1 与形象线（未提交）的冲突面

形象线已占：`config.py`(中段) · `main.py`(后台 loop 列表) · `models/__init__.py` ·
`models/resident.py` · `schemas/resident.py` · `services/sprite_service.py` ·
`routers/admin/__init__.py` · `alembic/env.py` · `seed/preset_characters.py` · `agent/main.py` ·
`tests/{test_deploy_compose,test_lifespan_background_tasks,test_sprite_service}.py` ·
前端 admin 面板 / `GameScene.ts` / Onboarding / Landing / `vite.config.ts` / `vitest.config.ts` /
`asset-provenance.json` · `.gitignore` · `THIRD_PARTY_NOTICES.md` · `docs/ROADMAP.md` ·
`deploy/backend/*`

**它完全没碰**：`civic / election / duty / coin / shop / proposal / policy / treasury_service` ·
`nightly_cron.py` · `ws/manager.py` · `agent/chat.py` · `app/lab`。**这片就是本批的活动空间。**

| 文件 | 线 1 S1-1 | 线 2 财政接线 | 形象线 | 处置 |
|---|---|---|---|---|
| `config.py` | 尾部追加 `rep_` 块 | **不碰**（读 policy，不加 flag） | 中段 `resident_sprite_*` 块 | 追加式，位置不同，手工拼 |
| `models/resident.py` | **不碰**（`meta_json` 已存在，零迁移） | 不碰 | 已改 | 无冲突 |
| `models/__init__.py` | 不碰（无新模型） | 不碰 | 加 1 行 | 无冲突 |
| `nightly_cron.py` | 新增 1 个独立块（`recompute`） | 不碰 | 不碰 | 线 1 独占 |
| `civic_service.py` | 改 `_npc_choice`（加信任项） | 不碰 | 不碰 | 线 1 独占 |
| `election_service.py` | 改 `open_election`（候选排序） | 不碰 | 不碰 | 线 1 独占 |
| `coin_service.py` | 加 `hold_pending` 声誉守卫 | **不碰** | 不碰 | 线 1 独占 |
| `duty_service.py` | 不碰 | 改 `_pay_wage` 读 policy | 不碰 | 线 2 独占 |
| `policy_service.py` / `treasury_service.py` | 不碰 | 线 2 独占 | 不碰 | 无 |
| `shop_service.py` / `shop_effects.py` | 不碰 | 线 2 独占（`tax_rate`） | 不碰 | 无 |
| 新迁移 | **无** | **无** | 050（未提交） | 本批零迁移 = 零多头风险 |

> **线 1 / 线 2 唯一的历史冲突点 `coin_service` 已消解**：S1-5 的 treasury 已经合并落地
> （`treasury_service.py` 已存在，`coin_service.treasury_*` 已就位），线 2 的税率接线只是
> 「把写死的 settings 换成 `PolicyService.get()`」，**不需要动 `coin_service`**。
> 线 1 的赊账守卫独占 `coin_service.hold_pending`。判定：**可以真并行。**

### 2.2 规格 anchors 已漂移，逐条重校（base=999e098 实测）

`KICKOFF_S1-1_reputation.md` 写作于 S2-1/S1-3 落地前，**多处行号与事实已过期**：

| 规格写法 | 实测（999e098） | 影响 |
|---|---|---|
| `_npc_choice` 在 `civic_service.py:180-227` | **`:280`**，且新增了 **`_npc_choice_legacy`（`:394`）** | option-0 修复（`c407832`）重写了该函数。**信任项加进 `:280` 的新实现，`_npc_choice_legacy` 保持字节不变**（它是门控回落路径） |
| `nightly_cron.py:28-230`，`RUN_HOUR=0/RUN_MINUTE=30` | 全文 **546 行**，**`RUN_HOUR=7 / RUN_MINUTE=0`**，`run_nightly_jobs(*, once_per_day=False)` 在 `:129` | 工程健康批 R3 补跑已落地。新块**追加在既有 job 块之后**，不动骨架 |
| `coin_service.hold_pending` 在 `:83-119` | **`:144`** | 行号漂移 |
| `_close_one` / `_execute_outcome` | **`:463` / `:557`** | S2-5 已插入 `_policy_threshold_verdict`(`:531`) 与 `_eligible_voter_count`(`:523`) |
| `install_mayor` / `current_mayor` | `election_service.py:127` / `:188` | 与规格一致 |
| `gossip_service.maybe_gossip` | `:49`（159 行） | 一致 |
| `witness_service.record_witnesses` | `:59`（135 行） | 一致 |
| `duty_service._pay_wage` | `:147` | 一致 |

**规格的三条硬事实仍然成立**（v1 零迁移落 `meta_json`、八卦无 sentiment 字段只能规则派生、
赊账是 greenfield），照做。

---

## 3. 暂缓清单（想开也别开）

| 工作项 | 为什么缓 |
|---|---|
| `skills_world_dev.db` 从 git 摘除 | 要改 `.gitignore`，形象线正压着该文件；且 `git rm --cached` 必须在主工作区执行 |
| 任何前端测试基建 | 形象线正在引入 `vitest.config.ts` + `frontend/package.json` 改动，直撞 |
| S1-2 越轨-制裁链 | 依赖 S1-1 落地（它才是「居民目击居民品行」这条输入源的提供方） |
| Lab 真实 Adapter / staging 灰度 | ROADMAP 阶段 4 受阻：生产身份、镜像、网络、存储、外部 attestation 未满足 |
| 25 张居民纹理授权 / provenance gate 转绿 | 形象线自己的下游；且卡在账户 Images API 403（见文末） |
| 夜间调度器抽象化 / per-job 调度 | 骨架刚被 R3 动过，等本批 nightly 追加块收口后单独做 |

---

## 4. 提示词 1 · S1-1 公共声誉轴

```
任务：实现社会扩展 S1-1 公共声誉轴。严格按 archive/2026-07-25/docs/kickoffs/KICKOFF_S1-1_reputation.md
执行——规格已含结论先行/现状锚点/任务切分/派生规则/签名/测试用例名/探针定义/不碰区域；
本提示词只补环境事实与并行纪律，两者冲突时以规格为准、偏差记报告。

工作区（已建好，直接用，不要另建）：
  cd /Volumes/data/dev/simverse-world/.worktrees/s1-1-reputation/backend
  source /Volumes/data/dev/simverse-world/backend/.venv/bin/activate
  python -c "import app,sys; p=app.__file__; assert '.worktrees/s1-1-reputation' in p, f'WRONG: {p}'; print('OK',p)"
  # 断言必须通过再继续。不要在此 worktree 里创建 backend/.env（会破坏 conftest 的测试隔离）。
分支 feat/s1-1-reputation 已从 999e098 拉好。

第 0 步（先做，不许跳）：
  python3 -m pytest tests/ -q > /tmp/s1-1-base.txt 2>&1; tail -3 /tmp/s1-1-base.txt
  收工用同一条命令 diff，硬门 = 相对基线零新增失败（不是 literal 0 failed）。

先读：规格全文（含末尾 anchors 清单）、archive/2026-07-25/docs/SOCIETY_EXPANSION_PLAN.md
的 :33 / :68 / :215 三行、services/{gossip,witness,relation,mood,civic,election,coin}_service.py、
models/{memory,resident}.py、tasks/nightly_cron.py 现状。

环境事实（规格写作后发生的变化，以此为准；规格 anchors 已漂移，逐条重校并记偏差）：
- civic_service.py 已被 option-0 修复（c407832）重写：_npc_choice 现在 :280，另有
  _npc_choice_legacy 在 :394。**声誉信任项只加进 :280 的新实现；_npc_choice_legacy 保持字节不变**
  （它是门控回落路径，动它等于把刚修好的 option-0 偏向重新引进来）。
  改完必须重跑 tests/test_civic_npc_choice*.py（option-0 的红/绿测试）确认零回归。
- nightly_cron.py 已被工程健康批 R3 改造：全文 546 行，RUN_HOUR=7 / RUN_MINUTE=0（不是规格写的 0/30），
  run_nightly_jobs 现在是 :129 且签名带 *, once_per_day=False，另有 _claim_run_date/_needs_catch_up/
  _anchor_passed/_anchor_date 一组补跑守卫。**你只在既有 job 块之后追加一个独立 try/except，
  绝不改动、移动、重排任何既有块，绝不碰 nightly_cron_loop 与 run_nightly_jobs 的顶部守卫。**
- coin_service.hold_pending 现在 :144（规格写 :83-119）。
- v1 零迁移仍然成立（落 Resident.meta_json['reputation']）。**本批禁止新增迁移**；
  若你判断非加不可，先停下来报告——050 已被并行的形象线占用但未提交，号段有雷。
- config.py 的 Settings 类中段已有形象线的 resident_sprite_* 块（未提交，你的 worktree 里看不到，
  但收口时会出现）。你的 rep_/REP_ 块一律**追加在类尾**，不改他人行。

要求：
1. 按规格逐任务 TDD（任务 1 recompute 聚合 → 2 投票信任项 → 3 候选排序 + 赊账守卫 → 4 只读 admin 端点），
   串行门不跳步：任务 1 全绿并提交后才开 2/3/4。一任务一提交带任务号（如 s1-1-1: reputation nightly aggregate）。
2. rep_enabled 默认 False，关闭时**字节级回落现状**：recompute 直接 return 0、_npc_choice 打分不含声誉项、
   open_election 候选集与排序逐字节同现状、hold_pending 只做余额检查。对照断言用同一份 fixture 跑两次。
3. 零新增 LLM 调用（写成测试断言）。八卦语气**纯规则派生**，不得假装读一个不存在的 sentiment 字段。
4. meta_json 写用 mood_service.decay_all（:83-91）同款范式：改副本 → flag_modified(r,'meta_json')。
   nightly 是单写者（main.py 的 run_background_tasks 门保证恰一个进程），不需要额外锁。
5. 赊账按规格只交付「信用判定原语 + 门控回落的 hold_pending 守卫接口」，**不编造赊账流水线**，
   缺口如实记进报告。
6. 测试：规格 §5 的单测 + 集成用例全实现，重点含 flag=False 字节级回落、零 LLM 断言、
   option-0 零回归三类；规格 §6 探针用 seeded fixture 出数。

红线：不合并不 push 不部署；不碰 _npc_choice_legacy、install_mayor/current_mayor 的存储语义、
duty/shop/policy/treasury_service、app/lab；不碰 models/resident.py（meta_json 已够用）；
不新增迁移；声誉数字永不进 NPC prompt（写成测试断言）；不提交 backend/skills_world_dev.db；
不在主工作区 /Volumes/data/dev/simverse-world 执行任何 git 写操作。

产出：docs/reports/feat-s1-1-reputation-report.md——任务状态表、全部偏差（含 anchors 行号漂移逐条对照）、
收口时需进 config.py / .env.example 的 REP_* 配置清单、探针数字、
以及「_npc_choice 新实现 vs legacy 的处置说明 + option-0 回归门证据」。
```

---

## 5. 提示词 2 · S2-5 四个财政条目接线

```
任务：把 S2-5 policies 里 4 个 fiscal_pending 占位条目真正接到 S1-5 的 TreasuryService 上。
依据 docs/reports/feat-s2-5-policies-report.md §5「待接 S1-5 的财政类条目清单」（该表已冻结）
与 docs/ROADMAP.md 近期优先级 #2 后半句。

工作区（已建好）：
  cd /Volumes/data/dev/simverse-world/.worktrees/s2-5-fiscal/backend
  source /Volumes/data/dev/simverse-world/backend/.venv/bin/activate
  python -c "import app; p=app.__file__; assert '.worktrees/s2-5-fiscal' in p, f'WRONG: {p}'; print('OK',p)"
  # 不要在此 worktree 里创建 backend/.env。
分支 feat/s2-5-fiscal-wiring 已从 999e098 拉好。

第 0 步：python3 -m pytest tests/ -q > /tmp/s2-5-fiscal-base.txt 2>&1; tail -3 /tmp/s2-5-fiscal-base.txt

先读：docs/reports/feat-s2-5-policies-report.md（尤其 §5 表与「接线前置」四条）、
docs/reports/feat-s1-5-treasury-report.md（TreasuryService 冻结签名）、
services/{policy_service,treasury_service,duty_service,shop_service}.py、shop_effects.py。

已冻结的对接面（实测，base=999e098）：
- treasury_service.py（207 行）：balance :53、tax_pending :62、tax :97、disburse :111、
  notify_changed :133、run_public_spending :174。签名已冻结，**不得修改**。
- policy_service.py（469 行）：PolicyService.get :209、get_group :218、list_all :226、
  apply_amend :313；FISCAL_PENDING_KEYS 常量与 tests/test_policy_service.py::
  test_fiscal_pending_keys_registered 是本线要拆掉的占位标记。
- duty_service._pay_wage :147（S1-5 已改过资金来源；S2-1 的镇长加成读 meta_json['mayor'] :157-158）。

四个条目（照报告 §5 的期望语义逐条接线，不自己发明）：
| 键 | tier | 接法 |
|---|---|---|
| tax_rate | simple_majority | 售货税基比率改读 PolicyService.get，落到 treasury_service.tax/tax_pending 的调用点 |
| medical_subsidy_sc | simple_majority | 就医公共补贴，走 treasury_service.disburse；余额不足按 S1-5 的既定语义降级/停发 |
| npc_default_wage_sc | simple_majority | duty_service._pay_wage 改读政策值（回落 settings.npc_default_wage_sc=5） |
| housing_development_scale | absolute_majority | 公共支出：disburse 扣款 + 触发住房容量提升 |

要求：
1. 逐条 TDD，一条一提交（如 s2-5-w1: wire tax_rate to TreasuryService）。
2. **门控矩阵是本线最容易错的地方，先写测试再写实现**：
   polis_policy_enabled × town_treasury_enabled 四种组合都要有断言。
   两个开关任一为 False 时，行为必须**字节级回落**到接线前（税率读 settings、工资读 settings、
   补贴与住房支出整块跳过）。这是本线的硬门。
3. 单向依赖：PolicyService 侧**只加读取（get）**，写路径仍走 amend；
   **不得**由财政侧反向写 policies（报告 §5 接线前置③）。
4. _pay_wage 里 S2-1 冻结的镇长加成回归门必须逐条不变，既有测试零改动通过。
5. 接线完成后拆掉 fiscal_pending 标记：FISCAL_PENDING_KEYS 清空或缩减、
   list_all()/GET /townhall/policies 的 fiscal_pending 标记随之消失、
   test_fiscal_pending_keys_registered 相应改写（不是删掉——改成断言「已接线的键不再标记 pending」）。
6. 全量 pytest 相对 /tmp/s2-5-fiscal-base.txt 零新增失败。

红线：不合并不 push 不部署；不改 TreasuryService 任何签名；不碰 civic/election/coin_service；
不碰 app/lab；不新增迁移；不给 policies 加列；政策与财政数字永不进 NPC prompt；
不提交 backend/skills_world_dev.db；不在主工作区执行 git 写操作。

产出：docs/reports/feat-s2-5-fiscal-wiring-report.md——四条目状态表、门控矩阵四组合的实测断言输出、
fiscal_pending 标记的清理说明、以及「余额不足语义」的最终落地口径（拒付 vs 部分支付）。
```

---

## 6. 提示词 3 · 部署批（048/049 + 工程健康批上 vm212）

```
任务：把已合并但未部署的三批代码上 vm212，定生产默认值，按需开闸，并观察。
对应 docs/ROADMAP.md 近期优先级 #2 前半 + #5。**本线是本批唯一有生产写权限的线。**

工作区（已建好，只用来写报告与 .env.example）：
  cd /Volumes/data/dev/simverse-world/.worktrees/deploy-0726
分支 ops/deploy-0726 已从 999e098 拉好。

范围（vm212，远端 /opt/skills-world，compose 在 /opt/skills-world/deploy）：
1. 部署 999e098 → alembic upgrade head（048_add_town_treasury → 049_add_policies）。
   **当前生产链头是 047**，本次要走两级。升级前必须先 pg_dump 备份并记录备份路径与大小。
2. 工程健康批（夜间补跑 R3 / 聊天锁 DB 侧回收 R4 / 五个 loop 心跳告警 P2）随同上线。
   这批的旋钮走 os.environ（LOOP_HEARTBEAT_* / SOCIAL_STATUS_*），本次一并补进
   deploy/backend/.env.example 与实际 .env，默认取保守值。
3. 生产默认值决策并登记：TOWN_TREASURY_ENABLED / POLIS_POLICY_ENABLED /
   POLIS_POLICY_APPROVAL_ENABLED。三个当前代码默认 False。
   **建议分两步：先部署但全部保持 False，确认零行为变化（字节级回落已有测试保证，
   生产再验一次），再单独开闸。**不要在同一次变更里既升迁移又开新行为。
4. 部署后观察（至少 24 真实小时 / 跨一个 07:00 北京锚点）：
   - GET /health/loops 五个 loop 心跳是否新鲜、是否误报
   - 夜间补跑台账：是否被触发过、是否同日重复跑
   - socializing 卡死回收：是否有回收记录、是否误杀活跃会话
   - 是否有新的 Sentry event / WARN 刷屏

关键前置（必须先确认，否则停下来报告）：
- 迁移 050_add_resident_sprites **不在 999e098 里**（形象线未提交），生产升到 049 即为 head。
  部署脚本若写死 head 检查，确认它拿到的是 049。
- deploy/backend/* 在形象线的未提交改动里有变更（含 resident-sprite-worker.env）。
  **本线部署的是 999e098 的版本，不含这些**；如果生产 compose 已被手工改过，先 diff 再动。

红线：
- 每一步写操作前先备份（pg_dump + .env 副本 + compose 副本），备份路径写进报告。
- 迁移只 upgrade，不 downgrade。遇到迁移失败立即停，回滚用备份，不手工改 alembic_version。
- 不改任何代码文件（除 deploy/backend/.env.example 的旋钮登记）。
- 不碰形象线相关的任何生产资源（static/media volume、resident-sprite-worker 容器）。
- 生产数据里的用户隐私字段（邮箱等）不得抄进报告，只留聚合数字与 slug。

产出：docs/reports/ops-deploy-2026-07-26-report.md——逐步命令与真实输出粘贴（不美化不估算）、
备份清单、三个开关的最终生产取值与理由、迁移前后 alembic current 输出、
24h 观察窗的四项结论（含「未触发」「样本不足」这类诚实结论）、
以及给 ROADMAP 的状态更新建议（阶段 2「S1-5/S2-5 未部署」这一格能否改写）。
```

---

## 7. 提示词 4 · 人口口径决策（注册人口 vs 自治居民）

```
任务：产出一份决策文档，回答 docs/ROADMAP.md 近期优先级 #4：
「明确玩家角色是否参与 NPC 自治，区分『注册人口』和『自治居民』，再决定 25-40 人扩容策略」。
**纯只读调研 + 决策文档，不改任何代码。**

工作区（已建好）：
  cd /Volumes/data/dev/simverse-world/.worktrees/population
分支 docs/population-scope-0726 已从 999e098 拉好。

调研范围（只读，逐条给 file:line 证据）：
1. 现状盘点：谁在参与自治？
   - agent/loop.py 的居民选取口径、civic_service.run_npc_voting(:140) 的投票人集合、
     _eligible_voter_count(:523) 的分母定义、election_service.open_election(:32) 的候选池、
     duty_service 的公职分配范围、relation/circle/gossip 的参与集合。
   - 玩家创建的居民（Resident.creator_id 非空）与 seed 的 11 位 NPC 在这些集合里是否被区别对待？
     现在是否有任何 is_npc / autonomous 标记？（grep 结论要写进文档，没有就如实说没有）
2. 三个数字要分清并各自取数：注册用户数 / Resident 行数 / 实际进入自治循环的居民数。
   生产数字走只读事务（BEGIN; SET TRANSACTION READ ONLY; ... COMMIT;）从 vm212 取，
   或者如果拿不到就用本地 dev 库并明确标注来源。
3. 成本口径：当前 $10/日全局预算下，26 人的 $/居民·天 是多少？
   线性外推到 40 人会不会撞预算？（读 docs/reports/ops-audit-2026-07-25B.md 的既有数字，
   不要重新跑任何 LLM）
4. 形象供给约束：M3 的 canonical 清单是 frontend/config/resident-sprite-generation.json 的
   **25 个静态 slot**（不是 11 位 seed NPC）。扩容到 40 人时形象从哪来？
   这条直接影响形象线 M3 的批次范围，是本文档最有下游价值的一节。

要交付的决策（每条给推荐 + 理由 + 反对意见 + 可逆性评估）：
A. 玩家创建的居民是否进入 NPC 自治循环（投票 / 公职 / 八卦 / 关系）？全进、全不进、还是分级？
B. 「注册人口」与「自治居民」是否需要成为显式的模型概念（新字段 / 新标记），
   还是继续用现有信号推导？如果要显式化，给出最小改动方案（但**本线不实现**）。
C. 25-40 扩容的分步方案：先到多少、门槛是什么、每步要先满足哪些前置（成本 / 形象 / 性能）。

红线：不改任何代码；不跑任何 LLM 调用；生产只读（禁 UPDATE/DELETE/INSERT/DDL/alembic/
docker compose 写操作）；隐私字段不进文档。
产出：docs/reports/docs-population-scope-0726-report.md——现状盘点（带 file:line）、三个数字、
成本外推、形象供给约束、三条决策 A/B/C，以及「给形象线 M3 的一句话结论」
（25 个 slot 到底对应谁，扩容后怎么办）。
```

---

## 8. 收口顺序（四条线完成后，主会话统一执行）

1. **线 4 人口口径**：零代码，随时并入。它的结论要先喂给形象线 M3。
2. **线 3 部署批**：`.env.example` 的旋钮登记并入；它的观察结论决定 ROADMAP 阶段 2 那格怎么写。
3. **线 2 财政接线**：改 `duty/shop/policy/treasury`，与线 1 无交集，先合。
4. **线 1 S1-1 声誉**：改 `civic/election/coin` + `nightly_cron` 追加块 + `config.py` 尾块，排最后。
5. **形象线单独收口**（见下）。
6. 全部合完：`alembic heads` 单头校验（硬门，应仍是单头）+ 统一补 `config.py` / `.env.example`
   （线 1 的 `REP_*`、线 3 的 `LOOP_HEARTBEAT_*` / `SOCIAL_STATUS_*`）+ 全量 pytest 一次
   + 更新 `docs/ROADMAP.md` + 把本批 `docs/reports/` 归入新的日期归档。

---

## 9. 形象线的悬空问题（需要单独处置）

形象线现在是**未提交的 76 条工作区改动**，这意味着：

- 它不是一条可合并的分支，没有 base，没有 diff 基准，也没法被 review。
- 本批四条线跑得越久，它将来的合并成本越高（`config.py` / `models/__init__.py` /
  `nightly_cron` 都会有新邻居）。
- 任何人在主工作区手滑一次 `git checkout` / `git stash` / `git clean -fdx`，900 行蒸发。
- 迁移 `050` 已被它占号但没进 git，本批必须绕开整个号段。

**建议尽快让形象线 agent 做一件事**：把当前工作区改动 commit 到独立分支
`feat/resident-sprites`（显式 `git add` 逐路径，**不带** `backend/skills_world_dev.db`），
主工作区回到干净的 `master`。之后它继续在自己的分支或 worktree 上测试。
这样五条线才是对等的、可按顺序收口的。

另外提醒：`git worktree list` 里还有两个僵尸（`simverse-world-port-044`、
`.claude/worktrees/optimistic-chebyshev-eb79f3`），`git worktree prune` 在受限 shell 下删不掉，
需要在你自己的终端跑一次。本批新建的 4 个 worktree 因为同样的删除限制被标成了 `locked`
（不影响提交/合并，只影响 `git worktree remove`）；将来要拆时先
`git worktree unlock .worktrees/<名>` 再 remove。

---

## 10. 不在代码里的阻塞点（只有项目所有者能解）

形象线的真正卡点不是代码：`.env` 中转认证与 `/models` 正常、能列出 `gpt-image-2`，
但 Images generations/edits **均返回 403**，签不出 capability receipt。
测试 agent 无论怎么跑都产不出 receipt，M1 的双候选盲评与 M3 的 275 次批次都无法开始。
**需要为该账户开通 Images API 权限，或更换一个能生成且能编辑的端点。**
这是当前投入产出比最高的一件事，且只有你能做。
