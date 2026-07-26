# S1-1 公共声誉轴(public reputation axis)— 工作线报告

- 分支:`feat/s1-1-reputation`,worktree `/Volumes/data/dev/simverse-world/.worktrees/s1-1-reputation`
- base:`999e098`(master,`fix(deploy): 内置居民阵容随部署自动同步`)
- 规格:`archive/2026-07-25/docs/kickoffs/KICKOFF_S1-1_reputation.md`
- 状态:**4 个任务 + §6 探针全部完成**,**未合并 / 未 push / 未部署 / 零迁移**

---

## 1. 任务状态表

| # | 任务 | 状态 | commit | 主要文件 |
|---|---|---|---|---|
| 1 | `reputation_service.recompute` nightly 聚合(核心,零 LLM,零迁移) | ✅ | `f61d7d1` | `backend/app/services/reputation_service.py`(新建)、`backend/app/tasks/nightly_cron.py`、`backend/app/config.py`、`backend/.env.example` |
| 2 | 投票信任项接线(`civic_service._npc_choice`) | ✅ | `7d8f489` | `backend/app/services/civic_service.py`、`backend/tests/test_m3_civic.py` |
| 3 | 候选人排序 + 赊账守卫 | ✅ | `31cff72` | `backend/app/services/election_service.py`、`backend/app/services/coin_service.py`、`backend/app/services/reputation_service.py` |
| 4 | 只读 admin 端点 `GET /admin/reputation` | ✅ | `ecafc73` | `backend/app/routers/admin/reputation.py`(新建)、`backend/app/routers/admin/__init__.py` |
| §6 | burn-in 探针(声誉分布 + 声誉—被选频率相关性) | ✅ | `8811a2e` | `backend/scripts/burnin_report.py`、`backend/tests/test_burnin_report_reputation.py` |

串行门遵守:任务 1 全绿并提交后才开 2,再 3,再 4,再探针;每任务先红后绿、独立提交,`git add` 全部显式列路径(无 `-A` / `.` / `commit -a`)。

## 2. 测试口径

- 新增用例:`tests/test_reputation_service.py`(20)+ `tests/test_burnin_report_reputation.py`(4)+ `tests/test_m3_civic.py`(+3)+ `tests/test_m6_election.py`(+2)+ `tests/test_coins.py`(+4)= **33 个**(`git diff` 计数与全量 passed 增量 +33 一致)。
- 三类硬断言全部落地:
  - **flag-off 字节级回落**:`test_recompute_disabled_is_noop`、`test_npc_choice_reputation_term_gated_off`(同一 fixture 跑两次逐位相等)、`test_open_election_ranks_by_reputation_on_tie`(门关时候选顺序逐位固定)、`test_hold_pending_credit_guard_is_gated_off`、`test_nightly_reputation_disabled_no_write`、e2e 的门关对照组。
  - **零新增 LLM**:`test_recompute_makes_zero_llm_calls` —— monkeypatch `app.llm.client.get_client` 为抛异常,`recompute` 仍成功。
  - **option-0 零回归**:见 §6。
- 另有红线断言:`test_reputation_never_enters_npc_prompt`(构造 score=-0.876543 的居民,断言 `build_decision_prompt` 产出的 system+user 里既无 `reputation` / `声誉` 字样也无该数字)。

全量口径见 §7。

## 3. 偏差清单

### 3.1 规格 anchors 行号漂移(逐条重校,以代码为准)

| 规格写的 anchor | 实际位置(base `999e098`) | 结论 |
|---|---|---|
| `civic_service._npc_choice:180-227` | **`:280`** 新实现(c407832 重写),`_npc_choice_legacy` 在 **`:394`**(本线改动后顺延到 `:405`) | 声誉项**只**加进 `:280` 的新实现;legacy 字节不变 |
| `civic_service.py:199-208` / `:216-222` / `:226`(打分三项 + argmax) | 已被 option-0 修复重写:A2 三档打分 `:319-336`、`_TRAIT_AFFINITY` `:338-341`、person-shaped 打分 `:352-371`、taste tie-break `:350` + `:390` | 规格描述的"三项打分 + 索引平票"已不成立;接法按新实现调整 |
| `civic_service.py:146`(门控顶部先例) | `:147`(`run_npc_voting` 的 `civic_polls_enabled`) | −1 行,语义不变 |
| `coin_service.hold_pending:83-119` | **`:144-185`**;真实签名是 `(db, user_id, amount, reason, *, terminalization_version="v1")`,不是规格写的 `(db, user_id, amount)` | 新参按 keyword-only 追加在尾 |
| `coin_service.py:94-98`(原子条件 UPDATE)/ `:100-103`(rowcount==0 → None) | `:164-169` / `:170-173` | 语义一致,原子范式未动 |
| `nightly_cron.run_nightly_jobs:28-230` | **`:129`**,签名带 `*, once_per_day: bool = False`;`RUN_HOUR=7 / RUN_MINUTE=0`(不是规格写的 00:30);另有 `_claim_run_date`/`_needs_catch_up`/`_anchor_passed`/`_anchor_date` 一组 R3 补跑守卫 | 只在既有 job 块之后追加一个独立 try/except;既有块零移动、`nightly_cron_loop` 与顶部守卫零触碰 |
| `nightly_cron.py:343-347`(00:30 触发) | `nightly_cron_loop` 在 `:519-546`,锚点 07:00 | 记录漂移,不涉及本线改动 |
| `election_service.install_mayor:127-172` | **`:139-197`**,且已含 S2-1 offices 双写(`polis_office_enabled`) | 只读不碰(本线一字未改) |
| `election_service.current_mayor:175-180` | `:200-217`,已是 offices-backed 读 | 只读不碰 |
| `main.py:85-93`(单进程注册) | `:86-90` | 单写者前提成立 |
| `config.py:375-378`(model_config / settings 单例) | **`:608-611`**(Settings 类已长到 594→611 行,中间已有 S2-1/S1-3/S1-5/S2-5 四组 flag) | `REP_` 块追加在类尾,不改他人行 |
| `routers/admin/economy.py:115-159`(每端点 `Depends(require_admin)`) | 该文件第一处 `require_admin` 在 `:9`;范式本身成立 | 照 `offices.py` 房规实现 |
| 迁移链头 `040_residents_creator_nullable` | 现链头 **`049_add_policies`**(045 已重命名为 `045_residents_creator_nullable`,046 offices / 047 issue_stances / 048 town_treasury / 049 policies 均已落地) | S1-1 零迁移,不参与号段争用 |
| 未漂移(逐条核实一致):`gossip_service.py:49/113/117-121/129-139`、`models/memory.py:53-85`、`witness_service.py:59-110`、`mood_service.decay_all:83-91`、`relation_service._clamp:60-63` 与 `relations_for:170-188`、`admin/middleware.py:10-33` | 同规格 | — |

### 3.2 规格假设已过时(写作后落地的并行线)

规格 §8 把 S1-3 / S1-5 / S2-1 / S2-5 列为"并行待落、会撞多头"。实际到 base `999e098` 时,**这四条线都已合并进 master**:`config.py` 已有 `POLIS_OFFICE_` / `POLIS_OPINION_` / `TOWN_` / `POLIS_POLICY_` 四组;`nightly_cron` 已有 opinion drift、office term_check、treasury 三个块;`election_service` 已含 offices 双写。所以本线**没有遇到规格预告的文件冲突**,只是按同一房规再追加一组。规格里"合并时按前缀分块追加"的协调建议对本线已无效(已是既成事实)。

### 3.3 实现层偏差(逐条,均有测试锁定)

| # | 规格怎么写 | 实际怎么做 | 为什么 |
|---|---|---|---|
| D1 | 任务 2:"对携带**候选人/提案人** slug 的选项加声誉项" | **只给候选人(person-shaped effect)选项加,不给 proposer 的 `scores[0]` 加** | 给 option 0 再叠一个正向项 = 把 c407832 刚修好的 option-0 结构性偏向重新引进来。`test_npc_choice_reputation_does_not_touch_the_proposer_nudge` 专门锁定 |
| D2 | 任务 2:"声誉经 `get_many` 批量取" | 用 `reputation_service.score_of(resident)` 直接读**已在手的** `meta_json` | 更严格地满足 §7 性能红线(读路径 **+0 查询**,连批量查询都不发)。`get_many` 仍实现并有单查询测试,留给未来不持有实体的消费端 |
| D3 | §2 公式:`new = (1-α)*prev + α*raw`,只在最后 clamp | **raw 先 clamp 到 `[rep_min, rep_max]` 再进 EMA**,末尾再 clamp 一次 | 否则"单晚移动 ≤ α×(max−min)"这个慢变量性质在极端 fixture 下不成立;`test_recompute_ema_smoothing` 把它变成可证的不变量 |
| D4 | 签名 `get_many(db, resident_ids: list[int]) -> dict[int, float]` | `list[str] -> dict[str, float]` | `Resident.id` 是 uuid 字符串,不是 int(规格笔误) |
| D5 | 签名 `hold_pending(db, user_id, amount, *, require_reputation=False)` | `hold_pending(db, user_id, amount, reason, *, terminalization_version="v1", require_reputation=False)` | 真实签名带 `reason` / `terminalization_version`;新参只能追加在尾 |
| D6 | 规格未定义"User 的声誉" | 新增 `credit_allowed_for_user(db, user_id)`:取该 user 名下居民(`creator_id`)的**最低**声誉;名下无居民 = 无证据 = 中性放行 | 声誉是 per-Resident,coin 账本是 per-User,原本没有映射(见 §5 缺口 G3) |
| D7 | 任务 4:`@router.get("/reputation")` | `APIRouter(prefix="/reputation")` + `@router.get("")` | 与 `offices.py` / `policies.py` 房规一致,对外路径同为 `/admin/reputation` |
| D8 | §6 探针 2 附"赊账被拒率 = 命中次数 / 总请求" | 出的是**结构性拒绝面**(score < 阈值的居民占比),输出文案里明写"非真实命中" | 赊账流水线不存在,没有请求流水可查 —— 红线要求不编造赊账流水线 |
| D9 | 规格未提 | `recompute` **每晚为全体居民写一条记录**(含无证据者,`samples=0`) | §6 探针要"遍历全体居民"出分布;无记录与 score=0 必须可区分 |
| D10 | 规格未提 | `recompute` **不过滤 `archived_at`**(被软归档的旧八卦仍计入证据) | 保持规则最小面;EMA 本身承担遗忘。若日后要"忘掉的谣言不再算数",是独立一刀 |

### 3.4 未做 / 跳过

- **无新增迁移**(规格 v1 即如此);`models/resident.py` 一字未改。
- **无新 WS 事件**(规格 §2 任务 1 明写 v1 不加,声誉由 S4-3 公报承载)。
- **没有任何生产调用方传 `require_reputation=True`** —— 见 §5 缺口 G1。
- 未碰:`_npc_choice_legacy`、`install_mayor`/`current_mayor` 存储语义、`duty/shop/policy/treasury_service`、`app/lab`、`gossip_service`/`witness_service`/`Memory` 写路径、`docs/ROADMAP.md`、`backend/skills_world_dev.db`。

## 4. 收口时需进 config.py / .env.example 的 `REP_*` 清单

两处**都已在本线落地**(`config.py` 追加在 `Settings` 类尾、`.env.example` 追加在文件尾),合并时按前缀整块拼接即可,与其它线零语义重叠。

| env key | Settings 字段 | 默认值 | 作用 |
|---|---|---|---|
| `REP_ENABLED` | `rep_enabled` | `false` | 主开关:nightly 聚合 + 全部消费端 |
| `REP_MIN` | `rep_min` | `-1.0` | score 下界 |
| `REP_MAX` | `rep_max` | `1.0` | score 上界 |
| `REP_NEUTRAL` | `rep_neutral` | `0.0` | flag-off / 无数据时的读默认 |
| `REP_EMA_ALPHA` | `rep_ema_alpha` | `0.3` | 慢变量 EMA 系数 |
| `REP_GOSSIP_BASE_TONE` | `rep_gossip_base_tone` | `-0.3` | 派生语气基线 |
| `REP_DISTORTION_PENALTY` | `rep_distortion_penalty` | `-0.2` | `distorted` 叠加惩罚 |
| `REP_MOOD_WEIGHT` | `rep_mood_weight` | `0.2` | 主体 mood valence 折入权重 |
| `REP_VOTE_TRUST_WEIGHT` | `rep_vote_trust_weight` | `1.0` | 投票信任打分权重 |
| `REP_CREDIT_MIN_SCORE` | `rep_credit_min_score` | `-0.3` | `credit_allowed` 放行阈值 |

> 注:`deploy/backend/.env.example` **未改**(该文件在别的线上已有未提交改动,避免抢写);部署时需要开声誉的话,把上表整块复制过去。

## 5. 缺口(如实记录,未交付)

- **G1 赊账流水线是 greenfield**:全代码仍无赊账/欠款/信用额度概念。本线只交付**信用判定原语**(`credit_allowed` / `credit_allowed_for_user`)+ **`hold_pending` 的门控守卫接口**,没有任何业务路径传 `require_reputation=True`。"低声誉者赊账被拒"这条验收在真实世界里**目前不可能被触发**,要等赊账机制立项。
- **G2 "居民目击居民品行"输入不存在**(规格缺口 A):`witness` 是居民→玩家、中性,v1 显式不计入(有测试锁定)。声誉的唯一真实输入是八卦 + 主体 mood,要等 S1-2 越轨-制裁链补链。
- **G3 声誉主体 vs 支付主体错位**:声誉挂在 Resident,coin 挂在 User。v1 用"名下居民最低分"桥接(D6),这是一个**未经产品确认的口径**,收口前建议拍板。
- **G4 默认阈值 `REP_CREDIT_MIN_SCORE=-0.3` 在当前信号强度下几乎不可达**:纯八卦派生的稳态下界 ≈ `mean(importance × tone / (1+hops))` = `0.7 × (−0.5) / 2 ≈ −0.175`,再叠满负 mood 才 ≈ `−0.375`。探针实测(§6)最低分 **−0.17**,拒绝面 **0/13**。也就是说**在 S1-2 补上更强的负向信号之前,信用闸门实际拦不住任何人**。要让它现在就有效,得调 `REP_CREDIT_MIN_SCORE`(如 `-0.1`)或 `REP_GOSSIP_BASE_TONE`。这是本线最重要的一条运营发现。
- **G5 声誉分布偏"全负"**:派生语气基线是负的,所以有八卦的人一律扣分,没人被议论反而 score=0 最高。"好名声"目前没有任何正向来源(除非 mood 长期为正)。规格如此设计(呼应 `realism_gossip_victim_valence`),但产品上值得复议。

## 6. `_npc_choice` 新实现 vs legacy 的处置 + option-0 回归门证据

**处置**:声誉信任项**只**加进 `:280` 的新实现(person-shaped 选项打分段内,整段包在 `if settings.rep_enabled:`);`_npc_choice_legacy`(现 `:405`)**字节不变**——它是 `CIVIC_NPC_CHOICE_LEGACY=true` 的门控回落路径,动它等于把刚修好的 option-0 偏向重新引进来。

`git diff 999e098..HEAD -- backend/app/services/civic_service.py --stat` = **`11 +++++++++++`,纯新增零删除**,插入点在 `_npc_choice` 内部;legacy 函数只是整体下移 11 行。

**回归门证据**(`tests/test_npc_choice_bias.py` + `tests/test_burnin_report_npc_vote.py`,option-0 的红/绿测试):

```
$ python3 -m pytest tests/test_m3_civic.py tests/test_npc_choice_bias.py \
      tests/test_burnin_report_npc_vote.py tests/test_m6_election.py \
      tests/test_reputation_service.py -q
46 passed, 1 warning in 12.34s
```

其中 `test_production_shape_option0_share_and_spread`(option-0 占比 ≤45%、≥3 个选项有票)、`test_election_shape_entropy_is_not_zero`(归一化熵 ≥0.75)、`test_legacy_kill_switch_restores_the_old_scorer`(legacy 仍精确复现 `[14,0,0,0]`)、`test_stable_unit_is_reproducible_across_processes`(digest 数值 `0.260063755221` 未变)全绿。

额外锁死:`test_npc_choice_reputation_does_not_touch_the_proposer_nudge` —— 提案人声誉不进 `scores[0]`。

## 7. §6 探针出数(seeded fixture,`tests/test_burnin_report_reputation.py`)

fixture:13 位居民(4 位候选人被议论强度递减:6/4/2/0 条,前两位失真;8 位普通选民 + 1 位传谣者),10 夜 `recompute`,再跑一场镇长选举 NPC 投票。

**开关开(`REP_ENABLED=true`)**

```
== 拟真探针（S1-1 验收：公共声誉轴）==
  声誉分布：13/13 位有记录，min/median/max = -0.17/0.0/0.0，均值 -0.034，方差 0.00409，偏度 -1.456 → 有分层
    直方图（0.2 宽）：{'[-0.2,0.0)': 3, '[0.0,0.2)': 10}
  声誉—被选频率相关性：Spearman ρ = 1.0（4 名候选人，合计 13 张 NPC 票）
  低声誉赊账拒绝面（结构性口径，非真实命中）：0/13 位居民 score < -0.3 → 0.0；赊账流水线尚不存在，无请求流水可查
```

**对照组(开关关,同一 fixture)**

```
== 拟真探针（S1-1 验收：公共声誉轴）==
  声誉分布 = -（13 位居民无一条声誉记录：nightly 聚合从未跑过 / 开关未开）
  声誉—被选频率相关性 = -（候选人样本不足：0 人 < 3，不对两个点谈相关）
  低声誉赊账拒绝面（结构性口径，非真实命中）：0/0 位居民 score < -0.3 → 0.0
```

读数:

1. **分布形态**:方差 `0.00409 > 0`、非退化 → 声誉机制确实产生了区分度;偏度 **−1.456**(左偏长尾)与规格预期的"右偏"相反 —— 因为派生语气基线为负,被议论越多越靠左,没人议论的一批堆在 0(见缺口 G5)。
2. **相关性**:Spearman **ρ = 1.0**(被议论最少者得票最多),方向与验收口径一致(高声誉 → 更常被选);样本只有 4 名候选人,是 seeded 演示量级,真数需 burn-in。
3. **赊账拒绝面 0/13** → 缺口 G4 的直接证据。

## 8. 全量测试与基线 diff

同一条命令、同一 worktree、同一 venv:

```
$ python3 -m pytest tests/ -q          # 基线(base 999e098,改动前) /tmp/s1-1-base.txt
51 failed, 1907 passed, 25 skipped, 11 deselected, 219 warnings, 17 errors in 433.93s (0:07:13)

$ python3 -m pytest tests/ -q          # 终态 /tmp/s1-1-final.txt
51 failed, 1940 passed, 25 skipped, 11 deselected, 223 warnings, 17 errors in 390.09s (0:06:30)
```

- failed **51 → 51**、errors **17 → 17**、skipped **25 → 25**、passed **1907 → 1940(+33,= 新增用例数)**。
- 失败集差集(`comm` on sorted `FAILED|ERROR` 行,把参数化 id 归一化后):**新增 0 条、消失 0 条**。
  唯一的原始行差异是 `test_lab_runtime_v2_store_auth.py::test_service_auth_rejects_untrusted_or_invalid_tokens[...]` ——
  同一条预存失败,参数 id 里嵌了当次现铸的 JWT(含时间戳),两次运行字符串必然不同,归一化后为同一条。
- 硬门口径 = **相对基线零新增失败**(本机含 lab-v2 需真 redis/testcontainers 的预存失败集,不是 literal 0 failed)→ **通过**。

## 9. 红线自查

| 红线 | 状态 |
|---|---|
| 不合并 / 不 push / 不部署 | ✅ 仅本地 commit |
| 不碰 `_npc_choice_legacy` | ✅ 字节不变(纯新增 diff) |
| 不碰 `install_mayor` / `current_mayor` 存储语义 | ✅ 一字未改 |
| 不碰 `duty/shop/policy/treasury_service`、`app/lab` | ✅ |
| 不碰 `models/resident.py` | ✅ 零改动(meta_json 够用) |
| 不新增迁移 | ✅ `alembic/versions/` 零新增 |
| 声誉数字永不进 NPC prompt | ✅ `test_reputation_never_enters_npc_prompt` |
| 零新增 LLM 调用 | ✅ `test_recompute_makes_zero_llm_calls` |
| 不提交 `backend/skills_world_dev.db` | ✅ 未 stage |
| 不碰 `docs/ROADMAP.md` | ✅ |
| 不在主工作区执行 git 写操作 | ✅ 全部命令在 worktree 内 |
| 不在本 worktree 建 `backend/.env` | ✅ 未创建 |
