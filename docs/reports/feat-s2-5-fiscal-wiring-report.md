# S2-5 财政条目接线 S1-5 TreasuryService — 工作线报告

- 分支:`feat/s2-5-fiscal-wiring`(worktree `/Volumes/data/dev/simverse-world/.worktrees/s2-5-fiscal`)
- base:`999e098`(master,S1-5 迁移 `048_add_town_treasury` / S2-5 迁移 `049_add_policies` 均已在 master)
- 依据:`docs/reports/feat-s2-5-policies-report.md` §5「待接 S1-5 的财政类条目清单」(冻结表)
  + `docs/reports/feat-s1-5-treasury-report.md` §7「给 S2-5 的接口冻结声明」
  + `docs/ROADMAP.md` 近期优先级 #2 后半句
- 日期:2026-07-26
- 状态:**3 条完全接线 + 1 条支付原语就位但缺事件源**(诚实登记,见 §3)
- 未合并 / 未 push / 未部署

---

## 1. 四条目状态表

| 键 | tier | 状态 | 接线路径 | commit |
|---|---|---|---|---|
| `tax_rate` | `simple_majority` | ✅ 完全接线 | `fiscal_policy.sales_tax_rate` → `shop_effects._resident_work_effect` → `_skim_town_tax` → `treasury_service.tax` | `1e68870` |
| `npc_default_wage_sc` | `simple_majority` | ✅ 完全接线 | `fiscal_policy.base_wage_sc` → `duty_service._pay_wage` → `treasury_service.disburse`(S1-5 funded wage) | `a1bf306` |
| `medical_subsidy_sc` | `simple_majority` | ⚠️ **部分**:支付原语就位,**无事件源** | `fiscal_policy.pay_medical_subsidy` → `treasury_service.disburse` + `coin_service.treasury_credit` | `0c2b243` |
| `housing_development_scale` | `absolute_majority` | ✅ 完全接线 | `nightly_cron` → `fiscal_policy.run_housing_development` → `treasury_service.disburse` + `map_data.assign_home` 容量提升 | `fda05f0` |

标记清理:`25c0193`。

**接线层是单一模块** `backend/app/services/fiscal_policy.py`——`policy_service`
管存储与审批、`treasury_service` 管钱,两边互不认识,只在这一处相遇。
单向依赖(§5 接线前置③)硬保:本模块**只调 `PolicyService.get`**,
写路径仍是 `apply_amend`(admin 端点 / `civic_service._execute_outcome`),
财政侧从不反向写 `policies`。`TreasuryService` 的任何签名未被修改。

### 改动文件

| 文件 | 改动 |
|---|---|
| `backend/app/services/fiscal_policy.py` | **新增**——接线层全部逻辑 |
| `backend/app/services/shop_effects.py` | 销售税调用点改读 `fiscal_policy.sales_tax_rate`(1 处) |
| `backend/app/services/duty_service.py` | `_pay_wage` 基准日薪分支(无 `wage_sc` perk 时读政策) |
| `backend/app/agent/map_data.py` | `assign_home` 加 `extra_capacity=0` 默认参数;`allocate_home` 取门控后的额外容量 |
| `backend/app/tasks/nightly_cron.py` | 追加住房开发块(独立门控 + 独立 `try/except`) |
| `backend/app/config.py` / `backend/.env.example` | 新增 `town_housing_unit_cost_sc` / `TOWN_HOUSING_UNIT_COST_SC`(默认 100) |
| `backend/app/services/policy_service.py` | `FISCAL_PENDING_KEYS` 缩减 + 新增 `FISCAL_WIRED_KEYS` |
| `backend/tests/test_fiscal_policy_wiring.py` | **新增** 53 条 |
| `backend/tests/test_policy_service.py` | `test_fiscal_pending_keys_registered` 改写 + 新增 2 条 |

---

## 2. 门控矩阵(本线硬门)

`polis_policy_enabled` × `town_treasury_enabled`,两个开关默认都是 `False`。
**任一为 False 时必须字节级回落到接线前**:税率读 `settings.town_tax_rate_sales`、
工资读 `settings.npc_default_wage_sc`、医疗补贴与住房开发整块跳过
(不查政策、不写库、不建镇账户行)。判定收在 `fiscal_policy.wiring_enabled()`
一处,`_policy_value()` 在门未全开时**直接返回默认值、不发查询**——
所以关闸世界的 DB 流量与接线前完全一致。

### 2.1 实测输出(真 sqlite DB + 真服务函数 + 真钱流动)

固定输入:policies 已播种并 amend 到 `tax_rate=0.25` / `npc_default_wage_sc=9` /
`medical_subsidy_sc=12` / `housing_development_scale=2`;
`settings` 侧 `town_tax_rate_sales=0.1` / `npc_default_wage_sc=5`;
镇库启动资金 1000 SC;售一件 20 SC 的居民手工件;给一名无 `wage_sc` perk 的
NPC 发一次工资。

```
[A 门全关]  polis_policy_enabled=False town_treasury_enabled=False
  税率(有效)          = 0.1          (settings=0.1, policy=0.25)
  售 20 SC 的手工件    → 抽税 0 / 卖家得 20
  日薪基准(有效)      = 5            (settings=5, policy=9)
  陈铁生工资入账      = 5
  就医补贴实付        = 0            (policy=12)
  住房开发新建单位    = 0 / 额外容量 = 0  (policy target=2)
  镇库余额            = 1000

[B 只开政策门]  polis_policy_enabled=True town_treasury_enabled=False
  税率(有效)          = 0.1          (settings=0.1, policy=0.25)
  售 20 SC 的手工件    → 抽税 0 / 卖家得 20
  日薪基准(有效)      = 5            (settings=5, policy=9)
  陈铁生工资入账      = 5
  就医补贴实付        = 0            (policy=12)
  住房开发新建单位    = 0 / 额外容量 = 0  (policy target=2)
  镇库余额            = 1000

[C 只开财政门]  polis_policy_enabled=False town_treasury_enabled=True
  税率(有效)          = 0.1          (settings=0.1, policy=0.25)
  售 20 SC 的手工件    → 抽税 2 / 卖家得 18
  日薪基准(有效)      = 5            (settings=5, policy=9)
  陈铁生工资入账      = 5
  就医补贴实付        = 0            (policy=12)
  住房开发新建单位    = 0 / 额外容量 = 0  (policy target=2)
  镇库余额            = 997

[D 门全开=接线生效]  polis_policy_enabled=True town_treasury_enabled=True
  税率(有效)          = 0.25          (settings=0.1, policy=0.25)
  售 20 SC 的手工件    → 抽税 5 / 卖家得 15
  日薪基准(有效)      = 9            (settings=5, policy=9)
  陈铁生工资入账      = 9
  就医补贴实付        = 12            (policy=12)
  住房开发新建单位    = 2 / 额外容量 = 2  (policy target=2)
  镇库余额            = 784
```

读法:

- **A / B**(`town_treasury_enabled=False`):镇库根本没开,不抽税、工资走 MINT
  (镇库 1000 分文未动)。B 证明**光开政策门不会咬合财政**——这是最容易写漏的一格。
- **C**(`polis_policy_enabled=False`):镇库开了,但税率仍是 settings 的 0.1
  (抽 2 而不是 5)、日薪仍是 settings 的 5。镇库 `1000 + 2 - 5 = 997` ✅
  补贴与住房整块跳过。
- **D**:三条接线全部咬合。镇库 `1000 + 5 - 9 - 12 - 200 = 784` ✅
  (住房 2 单位 × 单价 100 = 200)。

### 2.2 单测里的门控矩阵断言

四组合以 `@pytest.mark.parametrize` 逐条目铺开,不是只测 happy path:

| 测试 | 覆盖 |
|---|---|
| `test_sales_tax_rate_gate_matrix[4]` | 有效税率 |
| `test_base_wage_gate_matrix[4]` | 有效日薪基准 |
| `test_pay_wage_gate_matrix[4]` | `_pay_wage` 端到端 + 关闸时镇账户行不被创建 |
| `test_medical_subsidy_gate_matrix[4]` | 补贴支付 + 关闸时镇账户行不被创建 |
| `test_housing_development_gate_matrix[4]` | 住房支出 + funded 计数 |
| `test_allocate_home_gate_matrix[4]` | 住房容量:门未全开时即使 `system_config` 里躺着 funded 计数也一律当 0 |

---

## 3. `fiscal_pending` 标记清理说明

清理前 `FISCAL_PENDING_KEYS` 是 4 个键的 frozenset,`list_all()`、
`GET /townhall/policies`、`POST /admin/policies/{key}/amend` 三处都读它渲染
`fiscal_pending` 标记。

清理后拆成两个常量(三处消费点无需改代码,标记自动跟随):

```python
FISCAL_WIRED_KEYS = frozenset({
    "tax_rate", "npc_default_wage_sc", "housing_development_scale",
})
FISCAL_PENDING_KEYS = frozenset({"medical_subsidy_sc"})
```

`apply_amend` 里那条 "仅存储、未接线" 的 INFO 日志保留但改写文案,现在只会为
真正仍占位的键打印。

### 实测(真 uvicorn 进程 + 真 HTTP,DB 走临时文件 `/tmp/s25_fiscal_http.db`)

启动:`DEBUG=true AUTO_CREATE_TABLES=true RUN_BACKGROUND_TASKS=false
POLIS_POLICY_ENABLED=true POLIS_POLICY_APPROVAL_ENABLED=true
TOWN_TREASURY_ENABLED=true DATABASE_URL=sqlite+aiosqlite:////tmp/s25_fiscal_http.db
python -m uvicorn app.main:app --port 8742`

```
$ curl /health                       → {"status":"ok"}
$ PolicyService.seed_defaults()       → seeded: 17
$ curl /townhall/policies
enabled= True  rows= 17

key                           tier                  group         fiscal_pending
housing_development_scale     absolute_majority     fiscal        False
medical_subsidy_sc            simple_majority       fiscal        True
npc_default_wage_sc           simple_majority       fiscal        False
tax_rate                      simple_majority       fiscal        False

全表 fiscal_pending 为 true 的键: ['medical_subsidy_sc']
```

### 测试改写(不是删掉)

`tests/test_policy_service.py::test_fiscal_pending_keys_registered` 原本只断言
"占位清单 ⊆ catalog"。改写后守住的是**「接线 = 摘标记」**这个不变量:

- 两个集合互斥(一个键不可能既接线又占位);
- `FISCAL_WIRED_KEYS` 恰好等于那三个已接线的键;
- `FISCAL_PENDING_KEYS` 恰好等于 `{"medical_subsidy_sc"}`;
- 两者并集 == catalog 里 `group == "fiscal"` 的全部条目(一个不少)。

另新增两条:`test_wired_fiscal_keys_have_a_treasury_call_site`(接线守卫——
三个键各自都要有真实的 `TreasuryService` 调用点,否则"摘标记"是空头支票)与
`test_list_all_drops_fiscal_pending_on_wired_keys`(投影断言)。

---

## 4. 余额不足语义的最终落地口径

**统一口径 = 拒付(all-or-nothing),不做部分支付。**

| 场景 | 落地 |
|---|---|
| `medical_subsidy_sc` 补贴 12 SC / 镇库 5 SC | 返回 `0`,居民一分拿不到,镇库仍是 5(不被抽干) |
| `housing_development_scale` 造价 300 SC / 镇库 50 SC | 建成 0 个单位,镇库 50 分文未动,`funded` 计数不前进 → **下一晚税收补足后自动重试** |
| `_pay_wage`(S1-5 既有) | 未改动,仍按 `town_wage_unfunded_policy`(`skip`=欠薪 / `mint`=逃生门) |

理由三条:

1. **原子性**。`treasury_service.disburse` 是单条守卫 `UPDATE … WHERE
   balance_sc >= amount`;部分支付需要"先读余额再决定付多少"的两段式,天生有竞态。
2. **S1-5 自己的先例**就是全额拒付:`town_wage_unfunded_policy="skip"` 是**欠薪**
   而不是半薪。
3. **零行守卫命中绝不 `rollback`**(S1-5 硬规则 2 / `MissingGreenlet` 回归门)。
   两个新支出路径各有一条 `..._never_rolls_back` 断言用 `rollback` spy 钉死。

**唯一的例外来自 S1-5 自己**:`treasury_service.run_public_spending` 把
`town_public_works_daily_sc` **钳到当前余额**(部分支付)。那是一笔*预算*
——花多少都算数;本线两条是*账单*——12 SC 的补贴付 5 SC 没有意义,
2 套房的公投款项建 0.3 套房也没有意义。这条区分写进了 `fiscal_policy` 的模块
docstring。

---

## 5. 偏差与未交付缺口(诚实登记)

### D1 — `medical_subsidy_sc` 没有事件源(最重要的缺口)

报告 §5 的期望语义是"**每次就医**的公共补贴额"。实测代码库里**不存在任何
"就医"事件**:

- `app/agent/map_data.py` 里没有 `clinic` 地点;
- 没有健康 / 疾病 / 治疗系统(`grep -rn "medical|clinic|sick|illness|heal"` 只
  命中 `office_service.OFFICE_DEFS["doctor"]` 这条**纯数据定义**和政策 catalog 自身);
- `duty_service._WORK_HANDLERS` 里没有 doctor 处理器;
- `ROADMAP.md` 把「生命周期:健康、医疗、年龄、退休…」列在优先级 **#6 未开始**。

因此本线**没有发明一套健康系统**(那会远超 scope 且违反"照报告 §5 逐条接线,
不自己发明")。落地的是可被 S5-8 直接调用的**支付原语**:

```python
async def pay_medical_subsidy(db, *, slug: str, reason: str = "medical_subsidy",
                              resident=None) -> int
```

——门控矩阵、拒付语义、debit-before-credit、不 rollback、fail-open、
货币守恒全部有断言(7 条测试)。**条目本身仍留在 `FISCAL_PENDING_KEYS` 里**,
但占位理由从"等 S1-5 合并"改写成了真实原因:**缺事件源**。
S5-8 落地时只需在就医事件里加一行调用,不需要再碰财政侧。

> 任务书要求"FISCAL_PENDING_KEYS 清空或**缩减**"——本线选了缩减,4 → 1。

### D2 — 住房容量提升的建模方式(报告 §5 未指定)

§5 只写了"`disburse` 扣款 + 触发住房容量提升(§5.3)",没有指定容量存哪、怎么涨。
实测住房容量是 `map_data.LOCATIONS` 里的**静态数据**(19 处住所 / 合计 59 位),
没有任何动态扩容机制。本线的选择:

- **不新增迁移**(红线),已出资单位数落 `system_config`(group=`town`,
  key=`town_housing_funded_units`)——与 S1-5 的 `town_last_spend_at` 同一处;
- 镇出资单位建模为**公寓块的池化超容**:公寓是多户建筑,"镇又建了 3 套房"=
  公寓里多住得下 3 个人。基础容量**全满后**才启用超容,所以出资建房**不会**
  改变第 60 人之前任何一次分配的落点;
- 投放确定性:最空的公寓,平手按 `_HOUSING_ORDER`(**无 RNG**,守 seeded-RNG 纪律);
- `assign_home(occupied, extra_capacity=0)` 的默认参数让**未接线调用点逐字节不变**。

### D3 — 政策值是"目标总量"而非"每晚增量"

§5 写的是"本期新增住房单位数"。若按字面每晚加一次,nightly 会**每晚重复买同一批房**。
落地改成幂等语义:政策值 = **目标总量**,job 只为 `target − already_funded` 的
差额付钱。调低目标 → delta 为负 → no-op(不退款、不拆房、`funded` 不回退,
否则会把已经住进去的居民赶出来)。

### D4 — 新增了一个 settings 旋钮

`town_housing_unit_cost_sc`(默认 100)+ `.env.example` 同名行。
§5 没提造价,但"scale × 单价 = 支出金额"必须有个单价才落得了地。
`tests/test_env_example_consistency.py::test_every_settings_field_is_documented_or_allowlisted` 绿。

### D5 — `tax_rate` 只管售货税基

§5 原文"售货税基比率"。因此只接 `_resident_work_effect` 的销售税调用点;
送礼 / 打赏那个旋钮 `town_tax_rate_gift` **保持读 settings**,有专门断言
(`test_gift_tax_knob_is_not_governed_by_tax_rate`)。

### D6 — 每次发薪 / 每次售货多一次索引查询

门全开时,`_pay_wage` 与销售税各多一条 `policies.key`(有索引)的 SELECT。
两条都是**事件路径**而非 tick 循环:`_pay_wage` 受 `DUTY_WORK_COOLDOWN_HOURS=20`
的 redis 冷却限制(每居民每游戏日至多一次),销售税是每笔购买一次。
tick 循环未新增任何查询。另外 `_pay_wage` 里**先看 duty perk 再读政策**——
带 `wage_sc` perk 的居民零额外查询(有 `test_duty_wage_perk_still_wins_over_policy`
用"政策一被查询就炸"的桩钉死)。

### D7 — `townhall._finances` 里的 `npc_default_wage_sc` 仍读 settings

`app/routers/townhall.py:42` 的只读财务面板仍展示 settings 值。这是**展示面**
而非执行面,改它会碰到 S2-1/S1-5 共用的投影结构;不在 §5 清单内,本线未动。
登记为后续项。

---

## 6. 红线自检

| 红线 | 落地 |
|---|---|
| 不合并 / 不 push / 不部署 | ✅ 仅本地 worktree 提交 |
| 不改 `TreasuryService` 任何签名 | ✅ `treasury_service.py` **零改动**(`git diff --stat` 无该文件) |
| 不碰 `civic` / `election` / `coin_service` | ✅ 三者零改动 |
| 不碰 `app/lab` | ✅ 零改动 |
| 不新增迁移 | ✅ 无新文件进 `alembic/versions/`;新增状态落 `system_config` |
| 不给 `policies` 加列 | ✅ 模型零改动 |
| 政策与财政数字永不进 NPC prompt | ✅ `app/agent/` 里唯一改动是 `map_data.assign_home/allocate_home`(住房分配,不进 prompt);既有硬断言 `test_treasury_numbers_never_enter_npc_prompt` / `test_policy_probe_data_never_enters_npc_prompt` 仍绿 |
| 不提交 `backend/skills_world_dev.db` | ✅ 每次 `git add <显式路径>`,提交前后 `git status --porcelain` 核对 |
| 不碰 `docs/ROADMAP.md` | ✅ 只读 |
| 不在主工作区执行 git 写操作 | ✅ 全部命令在 worktree 内 |
| S2-1 镇长加成冻结门 | ✅ 仍读 `meta_json['mayor'] × election_mayor_wage_bonus`,只是基数换成政策值;`test_office_service.py` / `test_office_integration.py` / `test_duty_service.py` / `test_m1_economy.py` **零改动通过** |
| 零新增 LLM 边际成本 | ✅ 全部是查表 + 算术 + 一条 UPDATE |
| 单向依赖(§5 接线前置③) | ✅ `fiscal_policy` 只调 `PolicyService.get`;`grep -n apply_amend app/services/fiscal_policy.py` 唯一命中在 docstring 第 9 行(说明写路径归 `apply_amend`),无调用 |

红线区零改动实测:

```
$ git diff --stat 999e098 -- backend/app/services/treasury_service.py \
      backend/app/services/civic_service.py backend/app/services/election_service.py \
      backend/app/services/coin_service.py backend/app/lab backend/alembic
(空)
```

本线全部改动面:

```
 backend/.env.example                       |   7 +
 backend/app/agent/map_data.py              |  37 +-
 backend/app/config.py                      |   8 +
 backend/app/services/duty_service.py       |  14 +-
 backend/app/services/fiscal_policy.py      | 285 ++++++++++++
 backend/app/services/policy_service.py     |  30 +-
 backend/app/services/shop_effects.py       |   9 +-
 backend/app/tasks/nightly_cron.py          |  17 +
 backend/tests/test_fiscal_policy_wiring.py | 681 +++++++++++++++++++++++++++++
 backend/tests/test_policy_service.py       |  64 ++-
 10 files changed, 1132 insertions(+), 20 deletions(-)
```

---

## 7. 运行时证据补充:住房容量真的放得下第 60 人

真 DB(`/tmp/s25_fiscal_http.db`),把 19 处住所的 59 个基础房位全部塞满:

```
基础房位占满: 59 人
镇未出资时 allocate_home = None
公投通过 scale=2 → nightly 建成 2 个单位，镇库余额 300
第 60 人 allocate_home = apt_star (type= apartment )
```

---

## 8. 测试口径

新增用例:`tests/test_fiscal_policy_wiring.py` **53 条** +
`tests/test_policy_service.py` **新增 2 条**(另 1 条改写)= **+55 条**。

全量:`python3 -m pytest tests/ -q`

- 基线(`999e098`,`/tmp/s2-5-fiscal-base.txt`):
  `51 failed, 1907 passed, 25 skipped, 11 deselected, 219 warnings, 17 errors in 446.14s`
- 本线终态(`/tmp/s2-5-fiscal-final.txt`):
  `51 failed, 1962 passed, 25 skipped, 11 deselected, 219 warnings, 17 errors in 385.26s`

```
BASE : 51 failed, 1907 passed, 25 skipped, 11 deselected, 219 warnings, 17 errors in 446.14s (0:07:26)
FINAL: 51 failed, 1962 passed, 25 skipped, 11 deselected, 219 warnings, 17 errors in 385.26s (0:06:25)
```

`failed` / `skipped` / `deselected` / `errors` **四个数字逐一相等**;
`passed` 1907 → 1962 = **+55**,与本线新增用例数一致。

归一化失败集逐行 diff(去掉 `- reason` 尾巴与 parametrize 的 `[...]` id
——`test_lab_runtime_v2_store_auth` 的 id 里嵌了带时间戳的 JWT 字面量,每次
运行都不同,是同一条测试):

```
$ comm -13 /tmp/s2-5-base-norm.txt /tmp/s2-5-final-norm.txt   # 新增失败
(空)
$ comm -23 /tmp/s2-5-base-norm.txt /tmp/s2-5-final-norm.txt   # 消失的失败
(空)
```

失败集与基线**逐行完全一致(64 行归一化条目 / 68 行原始条目)** → 硬门通过:
相对基线**零新增失败**。

### 已知的预存失败(非本线引入)

- `tests/test_env_example_consistency.py::test_every_example_key_is_a_settings_field`
  ——`.env.example` 里有 38 个 `lab_*` 陈旧键没有对应 Settings 字段,基线里就是红的。
  本线新增的 `TOWN_HOUSING_UNIT_COST_SC` 走的是另一条不变量
  (`test_every_settings_field_is_documented_or_allowlisted`),该条**绿**。
- `tests/test_townhall.py::test_market_day_inactive_by_default` 在与
  `test_office_integration.py` 同进程运行时会失败。用 `999e098` 的原始
  `duty_service.py` / `shop_effects.py` 复跑同一选择集**同样失败** → 预存的
  进程级 active-event 缓存污染(S1-5 报告 §3.2.9 描述过同类现象),非本线引入;
  全量套件基线中不出现。

---

## 9. 未完成 / 后续项

| 项 | 说明 |
|---|---|
| `medical_subsidy_sc` 的事件源 | 归 ROADMAP #6「生命周期:健康、医疗」/ S5-8。支付原语已就位,接一行调用即可,财政侧不需再动 |
| `townhall._finances` 的 `npc_default_wage_sc` 展示值 | 仍读 settings,见 D7 |
| 生产默认值(是否开两个主闸、税率 / 造价取值) | 按 S1-5 §7 与 S2-5 §6「等拍板」,本线不改生产默认(两个开关仍默认 False) |
| 住房超容的可视化 | 前端地图仍按静态容量渲染;镇出资单位目前只影响分配逻辑,不改地图数据 |
| burn-in 探针 | 本线未加新探针。S1-5 的财政续航探针与 S2-5 的政策漂移探针已覆盖两侧,接线本身的观测量(有效税率 / 有效日薪)可在下一轮补 |
