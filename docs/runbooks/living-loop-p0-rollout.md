# Living Loop P0 封闭环境发布与回滚手册

> 状态：待执行手册。本文不表示功能已经部署、开闸或验证。
>
> 当前开发任务只允许代码、迁移、测试、文档、普通推送和 Draft PR；禁止合并，禁止操作 Cloudflare、VM、生产 `.env`、生产数据库或 Devpost。

产品与 API 合同见 [`../product/LIVING_LOOP_P0_SPEC.md`](../product/LIVING_LOOP_P0_SPEC.md)，事件与隐私合同见 [`../product/LIVING_LOOP_P0_EVENT_TAXONOMY.md`](../product/LIVING_LOOP_P0_EVENT_TAXONOMY.md)。实际执行证据填入 [`../reports/living-loop-p0-implementation.md`](../reports/living-loop-p0-implementation.md)。

## 1. 目标与边界

本手册只描述未来如何在隔离的封闭测试环境验证 Living Loop P0。它不授权生产部署。

| 阶段 | 允许动作 | 禁止动作 |
|---|---|---|
| 当前开发分支 | 本地/CI 测试、隔离数据库迁移往返、截图、普通推送、Draft PR | 合并、部署、生产配置或数据变更 |
| 封闭 staging | 在明确隔离的服务、数据库和测试账号上暗上并开闸 | 连接生产数据库、复用生产写入凭据、向真实用户开放 |
| 生产 | 本批不执行 | 所有生产发布、开闸和 schema 变更 |

Living Loop P0 只写 `living_loop_days` 和 `product_events`。若任何验证显示 Soul Coin、既有关系、市政投票、市场、Notification 已读状态、Digest、Challenge 会话或其他全局城市数据发生改变，立即停止并回滚。

## 2. 配置基线

所有环境的代码默认值和 `.env.example` 必须保持：

```dotenv
LIVING_LOOP_P0_ENABLED=false
LIVING_LOOP_P0_DELAY_SECONDS=28800
VITE_LIVING_LOOP_P0_ENABLED=false
```

- 后端 delay 合法范围为 `60..604800` 秒。
- 生产或常规 staging 使用默认 8 小时。
- 只有隔离 staging 的延迟后果验收可临时使用 `60` 秒；测试套件使用注入时钟，不真实 sleep。
- 后端开关是最终写入闸门；前端开关不能绕过后端关闭状态。
- 配置变更必须保留变更前快照，但不得把真实 `.env` 或秘密写入仓库或证据日志。

## 3. 开始前硬门

以下项目全部通过前，不得在封闭 staging 启动：

1. 分支为 `product/living-loop-p0-20260828`，基线是 `origin/challenge/webmcp-civic-copilot` 的已验证快进后代。
2. Draft PR 指向 `challenge/webmcp-civic-copilot`，保持 Draft、未合并。
3. 工作树干净，候选 SHA 与推送远端 SHA 一致；不得用脏工作树构建。
4. 后端全量 pytest、前端 Vitest、ESLint、TypeScript 和 build 全部通过。
5. `alembic heads` 返回唯一 HEAD；新迁移接到真实 HEAD，没有制造多头。
6. 隔离 PostgreSQL 已完成 `upgrade head → downgrade -1 → upgrade head`，且旧表/旧数据保持不变。
7. feature-off 测试证明 GET 不创建记录；跨用户隔离、并发创建、选择幂等、改选冲突、延迟披露和事件白名单均通过。
8. `/challenge` diagnostics 仍只注册一个诊断工具；Challenge/Town/Back/Refresh/Forward 生命周期回归通过。
9. 事件清理脚本默认 dry-run，90 天 cutoff 和显式 `--apply` 已通过测试。
10. 桌面和手机截图、已知限制、回滚材料与精确测试证据已准备。

任一门失败时停止，不用“基线也失败”或 SQLite 结果替代要求的 PostgreSQL 证据。

## 4. 隔离迁移演练

只在一次性或专用的 staging PostgreSQL 执行，先记录数据库标识、当前 revision、候选 SHA 和备份/快照位置。不得对生产数据库执行本节。

```bash
cd backend
alembic heads
alembic current
alembic upgrade head
alembic current
alembic downgrade -1
alembic current
alembic upgrade head
alembic current
```

验收：

- 初始与最终都是单头，新 revision 名称和 `down_revision` 与仓库事实一致。
- upgrade 只新增 `living_loop_days`、`product_events` 及其索引/约束。
- downgrade 只删除本 P0 对象。
- 既有用户、居民、经济、关系、Notification、Digest 和 Challenge 数据行数/抽样哈希不变。
- 第二次 upgrade 成功，唯一约束和索引恢复。

如果只能运行 SQLite，应在报告中写“SQLite 验证”，并把 PostgreSQL 标为未执行；不得声称 PostgreSQL 已通过。

## 5. Staging 暗上：开关全部关闭

1. 从精确候选 SHA 构建 staging 前后端，不使用本地未提交文件。
2. 执行迁移，保持三个开关为默认值。
3. 验证既有 `/`、`/play`、`/challenge`、`/town`、`/watch`、登录和 onboarding 行为。
4. 已认证测试账号直接调用 `GET /living-loop/today`，期望 `200`、`experiment.enabled=false`、`status=feature_disabled`。
5. 确认 `living_loop_days` 和 `product_events` 没有新增行。
6. 验证 `/today` 提供进入 `/play` 的安全降级，不白屏、不循环跳转。

暗上失败时恢复旧 staging 镜像/构建产物。迁移若纯新增且未写 P0 数据，可在隔离 staging 执行 downgrade；否则优先保留表并关闸。

## 6. Staging 分级开闸

每一步单独变更、验证和记录，不把迁移、后端开闸和前端开闸合成一个不可辨认的动作。

### 6.1 只开后端

```dotenv
LIVING_LOOP_P0_ENABLED=true
LIVING_LOOP_P0_DELAY_SECONDS=28800
VITE_LIVING_LOOP_P0_ENABLED=false
```

使用专用测试账号验收：

- 未完成 onboarding 不创建当日记录。
- 完成 onboarding 后首次 GET 创建一行；同日重复和并发 GET 仍只有一行。
- `/` 继续是旧 GamePage；直接 `/today` 可由测试/API 访问。
- Notification/Digest 查询失败时主决策仍可用，Notification 不被标已读。
- 三个选项各用独立测试账号验证；选择只影响 P0 表。

### 6.2 再开前端

```dotenv
LIVING_LOOP_P0_ENABLED=true
LIVING_LOOP_P0_DELAY_SECONDS=28800
VITE_LIVING_LOOP_P0_ENABLED=true
```

重新构建前端后验收：

- 未登录 LandingPage 新文案、主 CTA 登录 return path 和 `/town` 次 CTA 正确。
- 已登录、onboarding 完成的 `/` 进入 `/today`；`/play` 仍能直接进入地图。
- loading、error/retry、pending、confirmation、immediate-result、waiting、result-ready、result-viewed 状态完整。
- 320px 手机和桌面无横向溢出；键盘、焦点、ARIA 和 reduced-motion 可用。
- 遥测接口失败不阻断选择、结果查看或导航。

### 6.3 隔离环境延迟后果验收

只在隔离 staging 将 delay 临时改为安全下限：

```dotenv
LIVING_LOOP_P0_DELAY_SECONDS=60
```

1. 确认一个选择，保存 `choice_confirmed_at`、`result_available_at` 和立即结果。
2. 到期前 GET 和 result-viewed 都不能泄露延迟正文；提前 result-viewed 返回明确业务冲突。
3. 到期后首次 GET 或 result-viewed 只结算一次，写一个 `living_loop_result_settled`。
4. 首次 result-viewed 只写一个 `living_loop_result_first_viewed`；重试不覆盖时间。
5. 刷新、重新登录和另一浏览器读取相同状态。
6. 恢复 delay 为 `28800`，重新验证配置。

## 7. 事件、隐私和管理漏斗验收

- 客户端只能上报事件分类文档中的七个事件；三个服务端事件从客户端提交必须整批拒绝。
- 批次 `1..20`、32 KiB 上限、每 IP 每分钟 30 请求、全批拒绝和 `event_id` 幂等均通过。当前 SlowAPI 使用进程内存储，因此“30/min”是每 worker 上限；封闭验收必须固定单 worker，或先接入并验证共享 limiter backend，不能在默认双 worker 下声称集群全局 30/min。
- 事件行与日志不含姓名、邮箱、IP、完整 User-Agent、Token、聊天/记忆/日报/结果正文或自由文本。
- 管理端只读卡片显示 Today、决策查看、确认、到期、延迟查看、48h 回访、中位时间和三个选项分布。
- 非管理员访问失败；响应不含用户、会话、decision ID 或事件正文。
- 90 天清理默认 dry-run：

  ```bash
  cd backend
  python3 scripts/cleanup_product_events.py --retention-days 90
  ```

- 清理只删除 `product_events`。首次选择的 `choice_idempotency_key` 继续由 `living_loop_days` 全局唯一列保留；清理后必须复测原键精确重试仍成功、跨主体复用仍为 `409`。

- staging 测试数据只有在确认目标数据库且显式批准后才用 `--apply`。本开发任务不执行生产清理。

## 8. 观测与停止线

封闭测试至少观测：`/today` 错误率、选择确认率、到期/首次查看事件、数据库唯一冲突、接口 p50/p95、旧页面错误和 Challenge lifecycle。

任一条件触发立即关闭前端开关并停止新增测试账号：

- `/today` 错误率达到或超过 `1%`。
- 出现同一用户同一天多行、重复确认/结算/首次查看事件或改选覆盖。
- 到期前任何响应或日志出现延迟正文。
- P0 表以外的业务数据发生变化。
- 事件出现禁止数据、管理响应泄露单用户信息或清理范围不正确。
- `/play`、登录、onboarding、Challenge/Town/WebMCP 生命周期发生重大回归。

产品门槛（选择时间 ≤5 分钟、完成率 ≥70%、48h 回访 ≥40%）只能在封闭测试有真实样本后判断，不得用测试夹具冒充。

## 9. 回滚

### 9.1 行为回滚（首选）

1. 关闭并重新构建前端：`VITE_LIVING_LOOP_P0_ENABLED=false`。
2. 验证认证用户 `/` 恢复现有 GamePage，`/play` 正常。
3. 关闭后端：`LIVING_LOOP_P0_ENABLED=false`。
4. 验证 GET 返回 disabled 且不再创建记录；既有记录保留只读审计。
5. 将 delay 恢复默认 `28800`，保存不含秘密的配置差异证据。

### 9.2 代码回滚

恢复上一份已知健康的 staging 后端镜像和前端构建。先关闸再换代码，避免旧前端调用不兼容 API。验证健康、登录、`/play` 和 Challenge 生命周期。

### 9.3 Schema 回滚

紧急回滚不删除历史数据。只有在以下条件全部满足时，才可在隔离 staging 执行 `alembic downgrade -1`：

- 已确认不是生产数据库。
- 功能开关已关闭且应用已停止 P0 写入。
- 明确决定丢弃该 staging 的 P0 数据，并已保存必要证据。
- `alembic current` 精确等于本 P0 revision，downgrade 不会跨过其他迁移。

生产 schema downgrade 不在本任务授权范围内。

## 10. Draft PR 与交接

Draft PR 标题固定为：

`feat(product): add Living Loop P0 consequence-first home`

正文至少包含：起始/最终 SHA、目标分支、用户变化、API/数据库、迁移 revision、三个开关及默认值、每条测试命令精确结果、PostgreSQL 是否真实验证、桌面/手机截图、Challenge/WebMCP 回归、已知限制和本回滚手册。

PR 必须明确写明“未合并、未部署”。合并、staging 实际发布和任何生产动作都需要本任务之外的单独决定与授权。
