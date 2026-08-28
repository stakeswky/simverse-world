# Living Loop P0 实施与验证报告

规格：[产品与技术合同](../product/LIVING_LOOP_P0_SPEC.md) · [事件分类](../product/LIVING_LOOP_P0_EVENT_TAXONOMY.md) · [发布/回滚手册](../runbooks/living-loop-p0-rollout.md)

## 1. 结论

Living Loop P0 的产品代码、迁移、自动测试、文档和默认关闭开关已经完成；开发分支已交付并创建 Draft PR #16。开发分支未合并、未部署、未修改任何生产配置或数据。由于真实 PostgreSQL 往返、原生 Browser 历史矩阵和截图尚无可执行环境，本报告明确把“实现完成”和“发布证据门通过”分开：当前候选不是 release-ready，不得进入 staging。

| 项目 | 实际结果 |
|---|---|
| 代码实现 | COMPLETE；不等于发布门通过 |
| 后端全量测试 | `4580 passed, 6 skipped, 57 deselected, 489 warnings in 779.54s` |
| 前端全量测试/类型/lint/build | PASS |
| SQLite 迁移往返 | PASS |
| PostgreSQL 迁移往返 | NOT RUN：环境无 Docker、Podman、`psql`、`postgres` 或本地 PostgreSQL socket |
| Challenge/WebMCP 自动回归 | PASS |
| 真实 Browser 截图 | NOT CAPTURED：受控云浏览器禁止访问本地 loopback 和共享 `file:` 预览；未通过部署绕过 |
| staging 发布证据门 | BLOCKED：真实 PostgreSQL、原生 Browser 矩阵和截图未完成 |
| 分支推送 | DELIVERED：本地 HTTPS CLI 无凭据；授权 GitHub Git 对象连接逐提交重建、逐 tree 校验，并以 `force=false` 快进分支；无强推 |
| Draft PR | [#16](https://github.com/stakeswky/simverse-world/pull/16)，OPEN / DRAFT |
| 合并 | NO |
| 部署/生产修改 | NO |

开发阶段没有用夹具伪造选择完成率、48 小时回访率或错误率。真实产品门只可在后续独立封闭环境中评估。

## 2. Git 与基线身份

| 字段 | 实际证据 |
|---|---|
| 仓库 | `stakeswky/simverse-world` |
| 目标基线 | `challenge/webmcp-civic-copilot` |
| 最新 fetch | `2026-08-28T11:22:23Z`；`git fetch --all --prune` |
| 远端基线 SHA | `b377de5d611b7fe10e91875d2b80780b8daae336` |
| 方案观察 SHA | `b377de5d611b7fe10e91875d2b80780b8daae336` |
| 祖先/分叉证据 | `merge-base --is-ancestor` exit `0`；方案 SHA 与远端基线 `rev-list --left-right --count` 为 `0 0` |
| 远端同名分支预检 | absent；没有强推 |
| 开发分支 | `product/living-loop-p0-20260828` |
| 起始 SHA | `b377de5d611b7fe10e91875d2b80780b8daae336` |
| 代码与测试完成 SHA（evidence parent） | `a381bfd675431e7756f155ca55fac955e535e5a0` |
| 最终分支 SHA / tree SHA | 以 Draft PR head 与最终交接为准；不把包含本报告的提交 SHA 写进自身，避免不可解的 Git 哈希自引用 |
| 本地/远端一致 | 16 个 PR 创建前交付提交的 tree SHA 与本地逐提交一致；最终 evidence commit 使用同一流程，最终 head/tree 见 PR 与交接 |
| 最终工作树 | 最终 evidence commit 后以 `git status --short` 空输出复核，结果见交接 |

## 3. 实际提交序列

| SHA | Conventional Commit | 内容 |
|---|---|---|
| `def0f54371c45c61c17ef9e24138d6069fb7b37e` | `docs(product): define living loop p0 contract` | 权威实现规格与事件分类 |
| `c16cb2ea55c42ad1e8be5bd32b580b6460bbc5be` | `test(living-loop): define p0 regression gates` | API、迁移、前端和管理端初始红门 |
| `376bcff3b745fbfa51bb4ae92b583ea96e7d8b3c` | `test(living-loop): cover event retention cleanup` | 90 天清理合同 |
| `6618d906728b2eccbbc5c568630dc33acffd46c4` | `test(living-loop): harden authoritative event identity` | 权威事件碰撞回滚 |
| `292c9969d2b6ce395a5f9011e923d092442d6c4e` | `test(living-loop): enforce validation privacy and decision cohorts` | auth-first、隐私与 48h decision cohort |
| `3211c6fb2ea817fd29a9232da39f3b9fec802ed8` | `test(living-loop): reserve authoritative uuid namespace` | UUID4/UUID5 命名空间 |
| `4c6ff12bb06cd5afe87cec4405d8b0ff876e56cd` | `test(analytics): require resolvable ingestion schema` | OpenAPI schema 可解析性 |
| `d0e9673afe9a255a0857d5de86551b6236557bd3` | `test(privacy): hide database bind parameters` | 数据库异常参数隐藏 |
| `94fa4936551f2d3fe4104dfc8d1b10e2bd38ed7b` | `feat(living-loop): add persistent deterministic decision API` | 数据模型、069 迁移、状态机与用户 API |
| `795b490e16fa9e30d785c4ec182a153546c03db3` | `feat(analytics): add privacy-bounded p0 event ledger` | 严格事件 API、持久化与清理命令 |
| `9bfb74715c199c25a189c74ff39263adf3c6c315` | `feat(admin): expose living loop p0 funnel` | 管理员只读聚合漏斗 |
| `37f53e3b8266cb2adce4566f57db2cc443d43f2f` | `feat(frontend): add consequence-first today experience` | Landing、路由、Today 全状态、Admin UI |
| `228da4f998b6361702633cd7216b222058fc83c7` | `test(living-loop): close p0 lifecycle regression gaps` | 风险文案、隔日确认、长期幂等和焦点回归 |
| `c0c533b993bb6857c29252d960ad2dfbc8d98f33` | `test(living-loop): lock choice idempotency races` | 三类数据库选择键竞态与实际约束触发 |
| `a381bfd675431e7756f155ca55fac955e535e5a0` | `test(frontend): stabilize delayed result focus assertion` | 等待异步 effect 后断言焦点，消除全量并行负载下的测试竞态 |
| 本报告的提交 | `docs(living-loop): record rollout and verification evidence` | 路线图、runbook 和本报告；精确 SHA 由 Draft PR 提交列表和最终交接给出，不能嵌入提交自身 |

提交序列比最初建议更细，是因为独立 QA 找到的安全、披露和幂等边界分别先固化为失败测试，再实现修复。表内 SHA 是本地开发对象；本地 HTTPS remote 没有凭据，授权 GitHub 连接据此逐提交重建，提交作者/时间元数据由 GitHub 生成，因此远端 commit SHA 不同，但 16 个对应 tree SHA 全部逐一相同，提交消息和顺序保持不变。

## 4. 实际变更

### 4.1 用户可见

- 新增受保护 `/today`；前后端开关都严格以字符串/布尔 `true` 开启，默认关闭。
- Landing 主 CTA 保留 `/today` return path；`/town` 次入口和既有介绍保留。
- Today 提供加载、降级、setup、pending、二次确认、立即结果、服务端倒计时、ready/viewed 全状态。
- 三个选择展示背景、全局 stakes、确定性影响和逐选项明示风险。
- “今日一览”在窄屏先回答离开后、今日任务和后果时间；页面有单一 `h1`、native radio/fieldset、可见焦点、ARIA 和 reduced-motion。
- 隔日 `previous_result` 展示后幂等确认服务端 first-viewed，并从权威响应产生客户端送达事件。
- Admin Dashboard 底部新增只读 Living Loop 漏斗与三选项分布。

### 4.2 后端与数据

- `living_loop_days` 保存一用户一 UTC 日的版本化场景、选择、结果快照和状态时间。
- `choice_idempotency_key` 在决策行长期全局唯一，分析事件 90 天清理后仍保留首次选择绑定。
- `product_events` 只接受七个客户端事件的严格属性 schema；三个权威事件仅服务端写。
- choose、结算和 first-viewed 使用数据库 CAS/唯一约束及同事务权威事件；碰撞时整体回滚。
- 到期判断只用可注入服务端 UTC 时钟；到期前 API、错误和 SQL 日志不返回延迟正文。
- Notification/Digest 聚合 fail-open，不写 Notification `read_at`，不调用 LLM。
- 管理 API 只返回聚合，不返回 user、decision、session、姓名、邮箱或正文。
- 清理脚本默认 dry-run，只有显式 `--apply` 删除 `created_at < cutoff` 的事件。

最终文件统计：`50 files changed, 8356 insertions(+), 24 deletions(-)`。

## 5. Alembic 与数据库

| 项目 | 实际结果 |
|---|---|
| 实现前唯一 HEAD | `068_fix_theater_bounds` |
| 新 revision | `069_living_loop_p0` |
| `down_revision` | `068_fix_theater_bounds` |
| 最终唯一 HEAD | `069_living_loop_p0 (head)` |
| 新表 | `living_loop_days`、`product_events` |
| 主要约束 | daily 三列唯一；choice idempotency 全局唯一；event ID 全局唯一；FK cascade；状态/场景/choice/event CHECK |
| 既有 schema/data | migration 只 create/drop 两个 P0 表及其索引/约束；没有回填或修改旧表 |

SQLite `3.53.1` 一次性数据库使用脱敏形式 `DATABASE_URL=sqlite+aiosqlite:///... DEBUG=true`。测试只预建最小 `users` 父表，再 `stamp 068`，用于验证本次 069 一级迁移本身；它不是完整 068 schema，也不证明完整旧数据运行时兼容。

| 命令 | Exit | 结果 |
|---|---:|---|
| `alembic heads` | 0 | `069_living_loop_p0 (head)` |
| 预建最小 `users` 父表；`alembic stamp 068_fix_theater_bounds` | 0 | 仅为 069 外键提供父表并标记 revision |
| `alembic upgrade head` | 0 | `068 → 069`，两表存在 |
| `alembic downgrade -1` | 0 | `069 → 068` |
| `alembic upgrade head` | 0 | `068 → 069`，最终 revision `069_living_loop_p0` |

没有真实 PostgreSQL 服务或容器运行时，因此 PostgreSQL 只完成方言 DDL 编译审查，不能声称实机迁移或并发已验证。仓库从空 SQLite 跑完整历史仍会在既有 migration `003` 的 `ALTER CONSTRAINT` 处受 SQLite 能力限制；本次往返只证明 069 在上述最小父表 + stamped 068 前置条件下可执行。069 source 静态审查确认只创建/删除两个 P0 表及其索引/约束；真实旧 schema/data 不变仍须在隔离 PostgreSQL 验证。

## 6. API、状态机与安全证据

| 合同 | 自动/独立验证 | 状态 |
|---|---|---|
| auth、feature-off 零写入、setup-required | API 回归 | PASS |
| 首次创建、同日幂等、跨用户隔离 | API 回归 | PASS |
| 8 路并发 GET 收敛一行 | SQLite 多 session 回归 | PASS |
| 三个选项、完整 risk/快照、服务端影响 | API 回归 | PASS |
| 精确重试、新键同选项、改选冲突 | API 回归 | PASS |
| 跨 decision 同键竞态 | 正式 SQLite 并发回归：1×200、1×409 | PASS |
| choose 与客户端事件抢同键 | 正式 SQLite 并发回归：恰一方提交，状态/事件一致 | PASS |
| 同绑定并发重试 | 正式 SQLite 并发回归：2×200、1 事件 | PASS |
| 权威 UUID5 预占 | 状态和事件整体回滚 | PASS |
| 到期前不披露、到期后只结算一次 | 注入 `utc_now`，无真实 sleep | PASS |
| first-viewed 幂等、隔日结果确认 | 后端及 Today 回归 | PASS |
| Soul Coin/关系/Challenge 不变 | 不变量回归 | PASS |
| 事件白名单、20 条、32 KiB、限流、幂等 | 产品事件回归 | PASS |
| Admin 权限、decision cohort、PII 隔离 | 指标回归 | PASS |
| 删除账户清除 P0 行与包含居民名快照 | 既有删除回归 + FK ON 独立验证 | PASS |

## 7. 功能开关

| 开关 | 默认 | 示例配置 | 验证 |
|---|---:|---|---|
| `LIVING_LOOP_P0_ENABLED` | `false` | present | 关闭时 GET `200 feature_disabled` 且零写入 |
| `LIVING_LOOP_P0_DELAY_SECONDS` | `28800` | present | Settings 边界 `60..604800` |
| `VITE_LIVING_LOOP_P0_ENABLED` | `false` | present | 关闭时 `/`/`/play` 旧行为；`/today` 安全降级 |

## 8. 自动测试与构建

运行时：Python `3.12.13`，FastAPI `0.139.0`，Pydantic `2.13.4`，SQLAlchemy `2.0.51`；Node `24.19.0`，npm `11.9.0`。后端使用 `uv sync --frozen --extra dev` 产生的锁定 `.venv-lock`。

| 目录 | 命令 | Exit | 精确结果 |
|---|---|---:|---|
| `backend` | `env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy -u NO_PROXY -u no_proxy .venv-lock/bin/python -m pytest -q tests/` | `0` | `4580 passed, 6 skipped, 57 deselected, 489 warnings in 779.54s` |
| `backend` | `.venv-lock/bin/python -m pytest -q tests/test_cleanup_product_events.py tests/test_living_loop_api.py tests/test_living_loop_concurrency.py tests/test_living_loop_contract.py tests/test_living_loop_migration.py tests/test_living_loop_product_events.py tests/test_living_loop_product_metrics.py tests/test_living_loop_support.py` | 0 | `60 passed` |
| `backend` | `.venv-lock/bin/python -m pytest -q tests/test_living_loop_concurrency.py tests/test_living_loop_migration.py` | 0 | `6 passed`（并发/迁移子集复核） |
| `backend` | `.venv-lock/bin/python -m pytest -q tests/test_p1_fixes.py::test_delete_account_cleans_up_and_orphans_residents tests/test_account_deletion_sprite_run_fk.py` | 0 | `4 passed, 4 warnings in 0.87s` |
| `backend` | `alembic heads` | 0 | `069_living_loop_p0 (head)` |
| `frontend` | `npm test -- --run` | 0 | `82 files, 465 tests passed` |
| `frontend` | `npm run lint` | 0 | PASS，零 error |
| `frontend` | `npx tsc --noEmit` | 0 | PASS |
| `frontend` | `npm run build` | 0 | 940 modules；build PASS；仅已有 >500 KiB chunk warning |
| root | `git diff --check` | 0 | PASS |

前端最终样式修正后的定向复核命令：`npm test -- --run src/pages/TodayPage.test.tsx src/services/api/livingLoop.test.ts src/styles/today-page.responsive.test.ts src/App.test.tsx`，结果 `4 files, 52 tests passed`；随后 `npm run lint` 与 `npx tsc --noEmit` 均为 exit `0`。

后端第一次全量调用直接继承执行器的 `ALL_PROXY=socks5h://...`；锁定依赖没有 `socksio`，因此既有 `tests/test_llm_factory.py::test_get_client_system_returns_client` 在构造 SDK 客户端时失败。该轮在首错停止时为 `1 failed, 2673 passed, 5 skipped, 57 deselected`。清除当前 pytest 进程的代理环境后，`.venv-lock/bin/python -m pytest -q tests/test_llm_factory.py` 为 `4 passed`；没有修改产品代码或锁文件。上表全量结果来自同样清除代理变量的最终重跑。

## 9. Challenge / WebMCP 回归

| 验证 | 精确结果 | 环境 |
|---|---|---|
| `npm test -- --run src/App.test.tsx src/components/challenge/AgentActivityPanel.test.tsx src/components/challenge/HumanApprovalPanel.test.tsx src/components/challenge/OutcomeComparison.test.tsx src/pages/ChallengePage.test.tsx src/pages/WatchPage.test.tsx src/services/api/challenge.test.ts src/services/challengeTelemetry.test.ts src/stores/challengeStore.test.ts src/webmcp/activity.test.ts src/webmcp/challengeContract.test.ts src/webmcp/challengeToolSurfaceManager.test.ts src/webmcp/challengeTools.test.ts src/webmcp/registerChallengeStatusTool.test.ts` | `14 files, 141 tests passed` | Vitest/jsdom |
| `.venv-lock/bin/python -m pytest -q tests/challenge/` | `255 passed, 4 skipped, 1 warning in 7.32s` | pytest；真实 Redis 用例按环境 skip |
| `python3 -m unittest scripts.test_verify_webmcp_challenge_docs` | `Ran 4 tests ... OK` | Python unittest |
| `python3 scripts/verify-webmcp-challenge-docs.py --root .` | `challenge_docs_contract=PASS` | 本地静态合同检查 |
| Challenge/WebMCP 生产文件相对基线 | zero diff | `git diff --name-only b377de5d611b7fe10e91875d2b80780b8daae336 HEAD -- backend/app/challenge backend/tests/challenge frontend/src/components/challenge frontend/src/pages/ChallengePage.tsx frontend/src/services/api/challenge.ts frontend/src/services/challengeTelemetry.ts frontend/src/stores/challengeStore.ts frontend/src/webmcp`，输出为空 |
| 原生 ChatGPT Browser Back/Refresh/Forward 手工矩阵 | NOT RUN | 没有已部署候选 URL；本任务禁止部署，不能用 Vitest 冒充 |

一次文档 verifier 调用遗漏必填 `--root` 参数并以 usage exit `2` 结束；随即用上表完整命令重跑并通过。该操作没有写入。

## 10. UI、可访问性与截图

| 证据 | 结果 |
|---|---|
| Today 状态、键盘、ARIA、一次性焦点、reduced motion | Vitest/CSS 合同 PASS |
| 320px 横向溢出规则与移动摘要 | CSS 合同 PASS |
| 桌面 pending/immediate/result screenshot | NOT CAPTURED |
| 手机 320px screenshot | NOT CAPTURED |
| feature-disabled/Admin screenshot | NOT CAPTURED |

截图阻断证据：本地候选分别在 FastAPI `:8000` 与 Vite `:5173` 启动；受控云浏览器对 `http://127.0.0.1:5173` 返回 `ERR_BLOCKED_BY_CLIENT`，对同步共享 `file:` 预览按浏览器 URL 安全策略拒绝。安全策略禁止改用间接或替代浏览器表面绕过；本任务也明确禁止部署，因此没有伪造或用线上旧版本截图替代。

## 11. 隐私、保留与运维

- 七个客户端事件、三个服务端事件和逐事件属性全部严格枚举；额外键、自由文本和客户端服务端事件整批 `422`。
- 产品事件 API 先认证再解析/校验，422 不回显输入；SQLAlchemy engine 使用 `hide_parameters=True`。
- `event_id`/choice key 的重试、冲突、跨主体和竞态均有数据库约束及回归。
- 管理响应没有 user/decision/session ID、姓名、邮箱或事件正文。
- 90 天清理命令默认 dry-run；实际本地只读运行原始输出：`{"candidates": 0, "cutoff": "2026-05-30T10:47:05.464867Z", "deleted": 0, "mode": "dry-run"}`。
- 新增 diff 的秘密模式扫描仅命中测试哨兵字符串 `Bearer top-secret-must-not-echo`；它用于断言错误不泄密，不是真实凭据。没有专用 `gitleaks`/`trufflehog` binary。

## 12. 已知限制

| 项目 | 影响 | 下一步 |
|---|---|---|
| 无真实 PostgreSQL | 不能声明 PostgreSQL 迁移/锁竞争实机验证 | 在隔离 PostgreSQL 按 runbook 往返后才允许 staging |
| 无可访问候选 URL | 没有桌面/手机真实截图，也未跑原生 Browser 历史矩阵 | 保持 Draft；在独立可访问 preview/staging 补证据，不部署生产 |
| SlowAPI 使用进程内存储 | 默认双 worker 时严格上限为每 worker 30/min，不是集群全局 30/min | 封闭测试前评估共享 limiter backend；P0 保持现有依赖 |
| 产品指标无真实样本 | 无法判定 ≤5 分钟、≥70%、≥40%、<1% | 只用真实封闭测试样本评估 |

## 13. 回滚

行为回滚优先：先关闭并重建前端 `VITE_LIVING_LOOP_P0_ENABLED=false`，再关闭后端 `LIVING_LOOP_P0_ENABLED=false`；`/play` 永久保留。历史 P0 表默认保留，不在紧急回滚中删除。SQLite 已验证 downgrade 一级再 upgrade；生产 downgrade 未授权。完整步骤见 runbook。

## 14. Push 与 Draft PR

| 字段 | 实际值 |
|---|---|
| Push | `git push -u origin product/living-loop-p0-20260828` 因本地 HTTPS 无凭据 exit `128`，未写远端；随后授权 GitHub 连接重建 16 个提交并以 `force=false` 快进分支，最终 evidence commit 以同样方式追加 |
| 远端分支 SHA | 以 Draft PR head 与最终交接的 40 字符 SHA 为准；报告不嵌入包含自身的最终提交 SHA |
| PR 标题 | `feat(product): add Living Loop P0 consequence-first home` |
| PR | [#16 — feat(product): add Living Loop P0 consequence-first home](https://github.com/stakeswky/simverse-world/pull/16) |
| 状态 | OPEN / DRAFT；`merged=false` |
| Base ← head | `challenge/webmcp-civic-copilot` ← `product/living-loop-p0-20260828` |
| 合并 | NO |
| 部署/生产变更 | NO |

PR 证据回填：`2026-08-28T11:29:30Z`，Codex 实施代理。最终提交本身的 SHA/tree 由 Draft PR head 与最终交接提供，以避免 Git 自引用。
