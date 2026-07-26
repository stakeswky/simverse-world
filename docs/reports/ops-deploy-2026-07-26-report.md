# ops/deploy-0726 部署与观察报告（vm212）

- 执行线：`ops/deploy-0726`（基线 `999e098`）
- 执行时间：2026-07-26 02:00 – 02:30 UTC（= 北京时间 10:00 – 10:30）
- 目标主机：vm212（SSH 别名，地址见本地 `~/.ssh/config`；`/opt/skills-world`，compose 在 `/opt/skills-world/deploy`）
- 结论一句话：**开工清单的前置假设全部过期——999e098 已于 2026-07-25 17:12 UTC 在产，迁移已在 049，三个开关已全开。本次实际做的是"复核 + 工程健康批旋钮登记 + 首轮观察"，并在过程中发现一条 P0 数据丢失事故（12 个玩家角色被清空），见 §7。**

---

## 0. 与开工清单的偏差（先说清楚，后面全部据此改写）

| 开工清单的假设 | 实测 | 处置 |
|---|---|---|
| 当前生产链头是 047，本次要走两级（048→049） | **已经是 049（head）** | 第 1 步范围改写为"复核"，未执行任何 `alembic upgrade` |
| 999e098 未部署 | **已部署**，2026-07-25 17:12 UTC | 逐文件校验一致（§2） |
| 三个开关当前为 False，本次先部署保持 False 再单独开闸 | **三个都已经是 true**，2026-07-25 15:31 由 25B 线写入 | 未回滚；理由与证据见 §5 |
| 工程健康批旋钮未登记 | 属实，`deploy/backend/.env.example` 与生产 `.env` 都没有 | 本次补齐（§4） |
| 迁移 050 不在 999e098 里，049 即为 head | **属实**，已确认 | 无动作 |
| `deploy/backend/*` 生产 compose 可能被手工改过 | **未被手工改过**，与 999e098 逐字节一致 | 无动作 |

因此**本次没有"既升迁移又开新行为"的风险动作**——因为这两件事都已经在 2026-07-25 由别的线做完了（而且是**在同一次变更里同时做的**，违反了本线的红线，见 §5 的过程复盘）。

---

## 1. 迁移状态：`alembic current` 前后

本次**没有执行任何迁移动作**（已在 head）。以下是复核输出，前=后。

容器内：

```
$ ssh vm212 'cd /opt/skills-world && docker compose -f deploy/docker-compose.yml exec -T api alembic current'
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
049_add_policies (head)
```

直接读表交叉验证：

```
$ docker compose -f deploy/docker-compose.yml exec -T db psql -U postgres -d skills_world -c "select * from alembic_version;"
   version_num
------------------
 049_add_policies
(1 row)
```

本地 `999e098` 的迁移链末端：

```
$ ls backend/alembic/versions/ | sort | tail -8
043_add_lab_artifact_pipeline.py
044_merge_realism_and_lab_heads.py
045_residents_creator_nullable.py
046_add_offices.py
047_add_issue_stances.py
048_add_town_treasury.py
049_add_policies.py
b9c99304b867_initial_schema.py
```

远端 `/opt/skills-world/backend/alembic/versions/` 同样止于 049，**`050_add_resident_sprites.py` 不在生产**（形象线未提交，符合预期）。生产的 `bootstrap` 服务里写的是 `alembic upgrade head`，它拿到的 head 就是 049，没有写死版本号。

---

## 2. 部署一致性复核：生产跑的确实是 999e098

关键运行时文件 md5 逐一比对（本地 `999e098` vs 远端磁盘 vs **运行中容器内**），三者全等：

```
本地 (999e098)                          远端 /opt/skills-world/backend/
945ab2e0ff9d4dfa035d753817708bc2  app/tasks/loop_heartbeat.py          945ab2e0ff9d4dfa035d753817708bc2
8972aace5f89421b1e32e8185248e54d  app/services/social_status_recovery.py  8972aace5f89421b1e32e8185248e54d
30a73d437c3df23838e738fc0aab4c46  app/services/policy_service.py       30a73d437c3df23838e738fc0aab4c46
2f98d9e802c6b689ce9da11b9d027d9d  app/tasks/nightly_cron.py            2f98d9e802c6b689ce9da11b9d027d9d
a38fcea4bf729a7186d26fd6151722b2  app/main.py                          a38fcea4bf729a7186d26fd6151722b2
5b2ddba42e101c63ec14bbb73706d628  app/config.py                        5b2ddba42e101c63ec14bbb73706d628
```

运行中容器内（证明镜像里的代码就是这份，不是磁盘上放着但没生效）：

```
$ docker compose -f deploy/docker-compose.yml exec -T api md5sum /app/app/tasks/loop_heartbeat.py ...
945ab2e0ff9d4dfa035d753817708bc2  /app/app/tasks/loop_heartbeat.py
8972aace5f89421b1e32e8185248e54d  /app/app/services/social_status_recovery.py
30a73d437c3df23838e738fc0aab4c46  /app/app/services/policy_service.py
a38fcea4bf729a7186d26fd6151722b2  /app/app/main.py
5b2ddba42e101c63ec14bbb73706d628  /app/app/config.py
```

compose / Dockerfile 也与 999e098 逐字节一致：

```
本地  8743019e27b527bb94f98560a63f64e5  deploy/backend/docker-compose.yml
远端  8743019e27b527bb94f98560a63f64e5  /opt/skills-world/deploy/docker-compose.yml
本地  48a04fa081b0803d9e119364ef3797bb  deploy/backend/Dockerfile
远端  48a04fa081b0803d9e119364ef3797bb  /opt/skills-world/deploy/Dockerfile
```

全树 dry-run（按 `deploy.sh` 的 exclude 规则、`--checksum`）：只有 `tests/test_deploy_compose.py` 一个文件有差异——那正是 999e098 里跟着 compose 一起改的测试文件，纯测试、不进运行路径。运行时代码零差异。

```
$ rsync -avzn --delete --checksum ... backend/ vm212:/opt/skills-world/backend/
Transfer starting: 755 files
...
tests/test_deploy_compose.py
...
```

> ⚠️ 顺带发现的部署脚本隐患（本次未改，仅记录）：`deploy/backend/deploy.sh` 的 `rsync --delete` 的 exclude 列表里**没有** `.env` 和 `static/portraits/`，dry-run 显示它会 `deleting .env` 和 `deleting static/portraits/`。下次谁真跑 `deploy.sh` 会连带删掉远端 `backend/.env` 和已生成的头像目录。

容器与镜像：

```
$ docker compose ps -a
SERVICE        NAME                    STATE     STATUS
agent-worker   deploy-agent-worker-1   running   Up 9 hours
api            deploy-api-1            running   Up 9 hours
bootstrap      deploy-bootstrap-1      exited    Exited (0) 9 hours ago
db             deploy-db-1             running   Up 24 hours (healthy)
redis          deploy-redis-1          running   Up 24 hours (healthy)

$ docker inspect deploy-api-1 --format "{{.State.StartedAt}}"
2026-07-25T16:53:59.698212348Z
```

稳定性计数器（本轮观察窗内零重启、零 OOM）：

```
deploy-api-1: restarts=0 oom=false exit=0
deploy-agent-worker-1: restarts=0 oom=false exit=0
deploy-db-1: restarts=0 oom=false exit=0
deploy-redis-1: restarts=0 oom=false exit=0
```

`999e098` 新增的 `bootstrap` 服务编排断言在本地全绿：

```
$ uv run --frozen --all-extras pytest tests/test_deploy_compose.py -v
tests/test_deploy_compose.py::test_redis_service_present_with_healthcheck PASSED
tests/test_deploy_compose.py::test_api_delegates_background_tasks_to_worker PASSED
tests/test_deploy_compose.py::test_agent_worker_starts_by_default PASSED
tests/test_deploy_compose.py::test_api_and_worker_point_at_redis PASSED
tests/test_deploy_compose.py::test_api_and_worker_depend_on_redis PASSED
tests/test_deploy_compose.py::test_builtin_roster_bootstrap_precedes_api_and_worker PASSED
6 passed, 1 warning in 0.54s
```

---

## 3. 备份清单

本次写操作（只有一处：往生产 `.env` 追加旋钮）之前所做的全部备份：

| 备份 | 路径 | 大小 | 说明 |
|---|---|---|---|
| 生产 `.env` | `/opt/skills-world/deploy/.env.bak-ops0726-20260726-021511` | 2726 B | `cp -p`，改前原样 |
| 生产 compose | `/opt/skills-world/deploy/docker-compose.yml.bak-ops0726-20260726-021511` | 27432 B | `cp -p`，未改动，留档 |
| PostgreSQL 全量 | `/opt/skills-world/db-backup-ops0726-20260726-021511.sql.gz` | **4 240 190 B (4.05 MiB)** | md5 `d22b2871851ff254612bd00988ee8cf7` |

pg_dump 完整性验证（不是只看 exit code）：

```
$ gzip -t db-backup-ops0726-20260726-021511.sql.gz && echo "gzip OK"
gzip OK

$ gunzip -c ... | wc -c
11681870                       # 解压后 11.7 MB

$ gunzip -c ... | tail -3
\unrestrict TvSXSQTW...        # pg_dump 正常结尾标记

$ gunzip -c ... | grep -c "^CREATE TABLE"
75
$ psql -t -c "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE';"
75                             # 75/75，表数吻合

$ gunzip -c ... | grep -A3 "COPY public.alembic_version"
COPY public.alembic_version (version_num) FROM stdin;
049_add_policies
\.
```

**这个备份备的是哪个卷背后的库（应跨线情报要求明确记录）**：

```
$ docker inspect deploy-db-1 --format "{{json .Mounts}}"
[{"Type":"volume","Name":"deploy_pgdata",
  "Source":"/var/lib/docker/volumes/deploy_pgdata/_data",
  "Destination":"/var/lib/postgresql/data","RW":true}]
```

即 **`deploy_pgdata`（187M，PG_VERSION=16，pgvector/pgvector:pg16）**，这是 simverse 唯一的业务库卷。
另一个卷 `deploy_postgres_data`（1.1G）**未备份、未挂载读取、未做任何写操作**——原因见 §6，它不是 simverse 的数据。

⚠️ **重要提示：这份 4.05 MiB 的备份是"事故之后"的状态**，它不包含 2026-07-25 16:53 之前的世界数据。事故前的完好备份见 §7 的表格。

---

## 4. 工程健康批旋钮登记（本次唯一的写操作）

### 4.1 代码侧 `.env.example`

- `backend/.env.example`：**本来就已经登记齐全**（S1-5 / S2-5 / R4 / P2 共 18 个 key，行 514–559），且被 `tests/test_env_example_consistency.py` 守着。本次未改。
- `deploy/backend/.env.example`（运维面向的 docker 模板）：**一个都没有**。本次补齐，唯一改动文件。

```
$ git diff --stat
 deploy/backend/.env.example | 63 +++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 63 insertions(+)
```

补进去的 18 个 key（值取保守默认：三个开关 = false，工程健康批 = 代码内置默认）：

```
LOOP_HEARTBEAT_ALERT_COOLDOWN_MIN=60      SOCIAL_STATUS_RECOVERY_ENABLED=true
LOOP_HEARTBEAT_CHECK_INTERVAL_MIN=5       SOCIAL_STATUS_STALE_SECONDS=600
LOOP_HEARTBEAT_ENABLED=true               TOWN_PUBLIC_WORKS_DAILY_SC=0
LOOP_HEARTBEAT_MIN_STALE_SEC=900          TOWN_TAX_RATE_GIFT=0.0
LOOP_HEARTBEAT_STALE_FACTOR=3             TOWN_TAX_RATE_SALES=0.1
POLIS_POLICY_ABSOLUTE_MAJORITY_THRESHOLD=0.667   TOWN_TREASURY_ENABLED=false
POLIS_POLICY_APPROVAL_ENABLED=false       TOWN_WAGE_UNFUNDED_POLICY=skip
POLIS_POLICY_ENABLED=false                TOWN_WS_MIN_DELTA_SC=0
POLIS_POLICY_QUORUM_FRACTION=0.50
POLIS_POLICY_SIMPLE_MAJORITY_THRESHOLD=0.50
```

模板里同时写进了两条运维经验：①三个开关要"先部署 false → 确认零行为变化 → 单独一次变更再开"，不要和迁移同批；②`TOWN_WAGE_UNFUNDED_POLICY` 开局要用 `mint`，镇财政有存量后再收紧到 `skip`（`skip` + 0 余额 = 开闸当天全员欠薪）。

新增 key 全部能映射到真实 `Settings` 字段（复用 `test_env_example_consistency` 的检查逻辑跑在 deploy 模板上）：

```
total keys: 159
new keys registered: 18
deploy/.env.example keys with NO Settings field: ['lab_artifact_...', ... 'postgres_password']   # 57 个，全是 lab_*/postgres_password，与本次改动无关的存量问题
```

> `tests/test_env_example_consistency.py::test_every_example_key_is_a_settings_field` 在本地是 **FAILED**，但它读的是 `backend/.env.example`（本次未改），失败项全是 `lab_egress_*` / `lab_artifact_scanner_*`，**是本次改动之前就存在的失败**，与本报告无关。`git status --porcelain` 全程只有 `M deploy/backend/.env.example` 一行。

### 4.2 生产 `.env`

改前已 `cp -p` 备份（§3）。追加内容：

```
# ── 工程健康批旋钮登记 (ops/deploy-0726, 2026-07-26) ──
SOCIAL_STATUS_RECOVERY_ENABLED=true
SOCIAL_STATUS_STALE_SECONDS=600
LOOP_HEARTBEAT_ENABLED=true
LOOP_HEARTBEAT_STALE_FACTOR=3
LOOP_HEARTBEAT_MIN_STALE_SEC=900
LOOP_HEARTBEAT_ALERT_COOLDOWN_MIN=60
LOOP_HEARTBEAT_CHECK_INTERVAL_MIN=5
```

文件大小 2726 B → 3320 B。

**没有重启容器。** 理由：这 7 个值与代码内置默认值完全相同（下面 §4.3 的运行时探针已证明当前生效值就是这些），重启不会带来任何行为变化，却要重跑 `bootstrap` 服务（`alembic upgrade head && python -m seed.reset_builtin_residents`）——在 §7 的事故没查清之前，**不应该再触发任何一次 `reset_builtin_residents`**。这些登记值将在下一次自然重建容器时生效，届时生效值与现在一致。

不重启的前提下能做的验证已做满：

```
$ docker run --rm --env-file /opt/skills-world/deploy/.env alpine:latest env | grep -E "^(SOCIAL_STATUS|LOOP_HEARTBEAT|TOWN_TREASURY_ENABLED|POLIS_POLICY)" | sort
LOOP_HEARTBEAT_ALERT_COOLDOWN_MIN=60
LOOP_HEARTBEAT_CHECK_INTERVAL_MIN=5
LOOP_HEARTBEAT_ENABLED=true
LOOP_HEARTBEAT_MIN_STALE_SEC=900
LOOP_HEARTBEAT_STALE_FACTOR=3
POLIS_POLICY_APPROVAL_ENABLED=true
POLIS_POLICY_ENABLED=true
SOCIAL_STATUS_RECOVERY_ENABLED=true
SOCIAL_STATUS_STALE_SECONDS=600
TOWN_TREASURY_ENABLED=true
--- exit=0 ---

$ cd /opt/skills-world/deploy && docker compose config -q && echo "COMPOSE CONFIG OK"
COMPOSE CONFIG OK
```

（即：文件能被 docker 当 env-file 正常解析，compose 也能用新 `.env` 通过校验——下次 `up` 不会因为这段追加而失败。）

### 4.3 运行时生效值探针（只读）

在**正在跑的** agent-worker 里直接调函数取生效值：

```
$ docker compose exec -T agent-worker python -c "..."
R4 recovery_enabled = True
R4 stale_threshold_s = 600.0
P2 heartbeats_enabled = True
P2 cooldown_s = 3600.0 check_interval_s = 300.0
P2 thresholds = {'heat': 10800.0, 'event': 900.0, 'nightly': 259200.0, 'agent': 900.0, 'embedding_backfill': 10800.0}
gates: town_treasury True | policy True | policy_approval True
wage_unfunded_policy = mint | tax_sales = 0.1
```

---

## 5. 三个开关的最终生产取值与理由

| 开关 | 代码默认 | **生产当前值** | 谁设的 | 本次处置 |
|---|---|---|---|---|
| `TOWN_TREASURY_ENABLED` | False | **true** | 25B 线，2026-07-25 15:31 | 保持 true，不回滚 |
| `POLIS_POLICY_ENABLED` | False | **true** | 25B 线，2026-07-25 15:31 | 保持 true，不回滚 |
| `POLIS_POLICY_APPROVAL_ENABLED` | False | **true** | 25B 线，2026-07-25 15:31 | 保持 true，不回滚 |

配套旋钮（同批写入）：`TOWN_TAX_RATE_SALES=0.1`、`TOWN_TAX_RATE_GIFT=0.0`、`TOWN_WAGE_UNFUNDED_POLICY=mint`、`TOWN_PUBLIC_WORKS_DAILY_SC=0`、`TOWN_WS_MIN_DELTA_SC=0`。

### 过程复盘：本线红线被上一轮违反了

本线的硬要求是"**不要在同一次变更里既升迁移又开新行为**"。实际发生的是：2026-07-25 15:30 备份 → 15:31 写 `.env`（三开关一次性全开）→ 15:32 build → 16:53 起容器（迁移 048→049 与三个开关同时落地）。**迁移与开闸在同一次变更里完成，且三个开关一次全开，没有中间的"全 False 零行为变化"验证步。**这一条已经无法补做——只能记录，并要求下一批（S1-1 / S2-x）严格分两步。

### 为什么本次选择"保持 true"而不是回滚

1. 已经稳跑约 9.5 小时（16:53 → 02:30），期间零重启、零 OOM、agent-worker 全量日志里只有 3 条 WARNING/ERROR（§6.4），API 侧 0 条。
2. 回滚会产生新的不一致：`policies` 表已被 `seed_defaults` 写入 17 行、`town_treasuries` 已有 `town` 行。关掉存储门只是让读路径回落 `system_config`，但表里的数据不会退回去，等于制造一个"半开半关"的中间态。
3. `TOWN_WAGE_UNFUNDED_POLICY=mint` 已经把开闸的最大风险（镇财政开局 0 余额 + `skip` = 全员欠薪）挡住了——工资照发、销售税照进镇财政，行为与 S1-5 之前等价。
4. **§7 的数据事故未查清期间，任何"多余的"生产变更都会污染现场**。回滚三个开关需要重启容器，会再触发一次 `reset_builtin_residents`。

**回滚预案（若 Jimmy 决定回退）**：`cp /opt/skills-world/deploy/.env.bak-ops0726-20260726-021511 /opt/skills-world/deploy/.env` 会把三个开关连同本次登记一起退回 25B 状态（注意那份备份里三个开关**也是 true**，真要关得手工改成 false）；数据回退用 §7 表格里的事故前备份。

---

## 6. 部署后首轮观察（4 项）

采样窗口：2026-07-26 02:00 – 02:30 UTC。服务器时区 UTC，业务锚点 07:00 北京 = 23:00 UTC。
**下一个 07:00 北京锚点在 2026-07-26 23:00 UTC（约 21 小时后），本次观察窗跨不过去**——凡标"待复采"的项都必须在那之后再看一次。

### 6.1 `GET /health/loops` 五个 loop 心跳 — ✅ 通过，无误报

T1 采样（02:08 UTC）：

```json
{"status":"ok","enabled":true,"stale":[],"loops":{
 "heat":              {"state":"ok","age_seconds":853.1,  "threshold_seconds":10800.0, "last_beat":"2026-07-26T01:54:05.265281+00:00"},
 "event":             {"state":"ok","age_seconds":55.5,   "threshold_seconds":900.0,   "last_beat":"2026-07-26T02:07:22.865541+00:00"},
 "nightly":           {"state":"ok","age_seconds":11286.1,"threshold_seconds":259200.0,"last_beat":"2026-07-25T23:00:12.245644+00:00"},
 "agent":             {"state":"ok","age_seconds":20.7,   "threshold_seconds":900.0,   "last_beat":"2026-07-26T02:07:57.614531+00:00"},
 "embedding_backfill":{"state":"ok","age_seconds":546.2,  "threshold_seconds":10800.0, "last_beat":"2026-07-26T01:59:12.155609+00:00"}}}
```

T2 采样（02:24 UTC，16 分钟后）：

```json
{"status":"ok","enabled":true,"stale":[],"loops":{
 "heat":              {"state":"ok","age_seconds":1797.5, "last_beat":"2026-07-26T01:54:05.265281+00:00"},
 "event":             {"state":"ok","age_seconds":39.5,   "last_beat":"2026-07-26T02:23:23.320893+00:00"},
 "nightly":           {"state":"ok","age_seconds":12230.5,"last_beat":"2026-07-25T23:00:12.245644+00:00"},
 "agent":             {"state":"ok","age_seconds":51.7,   "last_beat":"2026-07-26T02:23:11.046010+00:00"},
 "embedding_backfill":{"state":"ok","age_seconds":1490.6, "last_beat":"2026-07-26T01:59:12.155609+00:00"}}}
```

Redis 侧交叉验证（心跳确实是 Redis key，不是内存态）：

```
$ docker exec deploy-redis-1 redis-cli --scan --pattern "sv:hb:*"
sv:hb:embedding_backfill / sv:hb:heat / sv:hb:nightly / sv:hb:event / sv:hb:agent
sv:hb:event = 2026-07-26T02:08:22.909428+00:00
```

判读：
- 五个 loop 全部 `ok`，`stale` 数组**空**，**零误报**。
- 两次采样之间 `event`（60s 节拍）和 `agent` 推进了，`heat` / `embedding_backfill`（3600s 节拍）和 `nightly`（86400s 节拍）没动——**这正是正确行为**，阈值分别是 10800s / 259200s，远没到。P2 的"下限 900s 防 60s 级 loop 误报"设计生效。
- 读写跨进程成立：心跳由 agent-worker 写，`/health/loops` 由 api 进程读，取到了。
- **待复采**：`nightly` 的 threshold 是 259200s（72h），本轮只覆盖 9.5h，"nightly loop 死了会不会按时告警"这条**没有被真实检验过**（样本不足）。需要在 2026-07-26 23:00 UTC 锚点之后再采一次，确认 `nightly` 的 `last_beat` 刷新到新锚点。

### 6.2 夜间补跑台账（R3）— ✅ **真实触发过一次，且没有同日重复跑**

这是本轮观察里最硬的一条证据：**R3 修的正是"部署窗口跨过 07:00 锚点导致整天夜间批次静默丢失"，而这次部署恰好跨了。**

```
$ docker logs deploy-agent-worker-1 | grep -inE "nightly|catch"
8:2026-07-25 15:32:53,281 WARNING app.tasks.nightly_cron: nightly: anchor 07:00 for 2026-07-25 already passed with no recorded run (restart/downtime) — catching up now
24:2026-07-25 15:33:04,103 INFO app.tasks.nightly_cron: Nightly digest ready: 2026-07-25 村落日报
80:2026-07-25 15:33:50,658 INFO app.tasks.nightly_cron: Realism P2: detected 2 social circles
2808:2026-07-25 23:00:00,062 INFO app.tasks.nightly_cron: Nightly digest ready: 2026-07-25 村落日报
2812:2026-07-25 23:00:11,915 INFO app.tasks.nightly_cron: Scheduled 1 world events
2813:2026-07-25 23:00:12,007 INFO app.tasks.nightly_cron: Advanced 1 story-arc milestones
2814:2026-07-25 23:00:12,076 INFO app.tasks.nightly_cron: 33 NPC civic votes cast
2815:2026-07-25 23:00:12,235 INFO app.tasks.nightly_cron: Realism P2: detected 1 social circles
```

Redis 台账：

```
$ docker exec deploy-redis-1 redis-cli get sv:nightly:last_run_date
2026-07-26
$ ... get sv:nightly:last_goal_week   → 117
$ ... get sv:nightly:last_decay_week  → 117
```

判读：
- **补跑被触发过**：15:32:53 的 WARNING 明确说 `anchor 07:00 for 2026-07-25 already passed with no recorded run` 并立刻补跑，15:33:04 产出了日报。这一天的夜间批次没有丢——**R3 在生产上第一次就救了一天的数据**。
- **没有同日重复跑**：全量日志里 `nightly_cron` 只出现 8 行，恰好对应两个批次（15:33 的补跑 = 锚点日 2026-07-25，23:00 的定时 = 锚点日 2026-07-26）。台账现在停在 `2026-07-26`，与 23:00 UTC = 07:00 北京 Jul-26 一致。`once_per_day` 的 SET NX 幂等生效。
- loop 只有一个属主：api 容器日志里 `nightly` 关键字 0 命中，说明后台 loop 只跑在 agent-worker，不存在双实例重复跑。
- **待复采**：还没观察到"连续两天正常锚点"。需在 2026-07-26 23:00 UTC 之后确认台账翻到 `2026-07-27` 且只跑一次。

### 6.3 socializing 卡死回收（R4）— ⚪ **未触发（无样本），且零误杀**

```
$ psql -c "select status, count(*) from residents group by status;"
 status  | count
---------+-------
 idle    |    10
 walking |     1

$ docker logs deploy-api-1 deploy-agent-worker-1 | grep -iE "social_status|socializ|recover"
（两个容器都是 0 命中）
```

判读：
- **回收器确实在跑**：R4 的 sweep 挂在 `heat_cron` 循环体里、`await beat("heat")` **之前**。heat 心跳新鲜（01:54，节拍 3600s），说明 sweep 那一段每小时都完整走完了。
- **回收记录：0 条**。日志里既没有 `recycled N stale socializing lock(s) (R4)`，也没有 `stale socializing recovery failed`。
- **误杀：0 次**。当前 `socializing` 状态的居民数为 0，本来就没有可回收对象——这是"没有样本"，不是"回收器没用"。
- 运行时生效阈值已探针确认：`recovery_enabled = True`，`stale_threshold_s = 600.0`（对齐 `SOCIAL_LOCK_TTL`）。
- **诚实结论：样本不足。**本轮无法证明 R4 在真实卡死场景下能正确回收，只能证明它在跑、没报错、没误杀。要真正验证需要制造一次 worker 猝死（不在本次授权范围）或等一次自然发生的卡死。

### 6.4 新 Sentry event / WARN 刷屏 — ✅ 无刷屏

```
$ docker logs deploy-agent-worker-1 | grep -cE " WARNING | ERROR "
3
$ docker logs deploy-api-1 | grep -cE " WARNING | ERROR "
0
```

agent-worker 全部 3 条（9.5 小时、5318 行日志）：

```
1  WARNING app.tasks.nightly_cron: nightly: anchor 07:00 for 2026-07-25 already passed with no recorded run (restart/downti…
1  WARNING app.slow_query: slow query 510ms: UPDATE memories SET embedding = NULL WHERE type = 'event' AND embedding IS NOT…
1  WARNING app.agent.phases.plan.basic: Plan generation failed for lin-wanqiu: No parseable JSON in plan response: {
```

判读：
- 第 1 条是 R3 补跑的**预期告警**（设计如此，不是故障）。
- 第 2 条 510ms 只比 `SLOW_QUERY_MS=500` 高 10ms，单次，无复现。
- 第 3 条是 LLM 偶发返回不可解析 JSON，单次，已被 fail-open 兜住。
- **无 WARN 刷屏，无 ERROR，无 Traceback。**
- Sentry：`SENTRY_DSN` 已配、`SENTRY_ENVIRONMENT=vm212-test`，日志显示 `Sentry initialised (component=agent-worker)`。P2 的 Sentry 事件只在心跳过期时发，而本轮 `stale` 恒为空 → **推断本轮无新 P2 Sentry event**。
- **诚实限制：我没有 Sentry API token，无法直接查询 Sentry 项目里的 event 列表。**上面是从日志侧反推的结论，不是 Sentry 侧的直接证据。要给出"确实零新 event"的硬结论，需要有人用 Sentry 控制台或 API 复核 `jiamin/simverse-backend` 项目 `vm212-test` 环境 2026-07-25 15:30 之后的 event。

### 6.5 顺带采到的开闸后业务侧数据（非任务四项，供参考）

`policies` 表已按 S2-5 四级矩阵种子化 17 行，工作正常：

```
             key              |        tier         | version
------------------------------+---------------------+---------
 approval_routing             | absolute_majority   |       1
 business_hours               | simple_majority     |       1
 civic_poll_days              | administrative      |       1
 curfew_hours                 | simple_majority     |       1
 election_exists              | constitutional_core |       1
 election_interval_days       | absolute_majority   |       1
 exile_right                  | constitutional_core |       1
 housing_development_scale    | absolute_majority   |       1
 lab_approval_gate            | constitutional_core |       1
 lab_envelope_definition      | constitutional_core |       1
 lab_self_governance_immunity | constitutional_core |       1
 market_day_discount          | administrative      |       1
 market_day_weekday           | administrative      |       1
 medical_subsidy_sc           | simple_majority     |       1
 npc_default_wage_sc          | simple_majority     |       1
 recall_threshold             | absolute_majority   |       1
 tax_rate                     | simple_majority     |       1
```

`town_treasuries`：

```
 key  | balance_sc |          updated_at
------+------------+-------------------------------
 town |          0 | 2026-07-25 15:36:18.416435+00
```

→ 镇财政余额**仍为 0**，`updated_at` 自 15:36 以来没动过。销售税率 0.1 已开，但 9.5 小时里没有产生任何居民售货收入。**样本不足**，需跨锚点复采一次看税入是否开始进账。目前 `TOWN_WAGE_UNFUNDED_POLICY=mint` 挡着，余额 0 不会导致欠薪。

NPC 投票分布（顺带验证 `c407832` 的 option-0 偏向修复在生产上确实没有退化）：

```
             q              | ord |     label     | npc_votes
----------------------------+-----+---------------+-----------
 在南苑空地兴建一座邮局     |   1 | 赞成兴建      |        20
 在南苑空地兴建一座邮局     |   2 | 暂缓,维持现状 |         5
 在东岸花园兴建一座剧院     |   1 | 赞成兴建      |        19
 在东岸花园兴建一座剧院     |   2 | 暂缓,维持现状 |         6
 镇长选举:谁来当下一任镇长? |   1 | 克劳斯        |        17
 镇长选举:谁来当下一任镇长? |   2 | 夜风侦探      |         2
 镇长选举:谁来当下一任镇长? |   3 | 伊莎贝拉      |         5
 镇长选举:谁来当下一任镇长? |   4 | 亚当          |         1
```

→ 4 选项的选举票分布是 17/2/5/1，**不是 25/0/0/0 的 option-0 独占**，修复在生产上成立。三个 poll 全部 `open`，`closes_at = 2026-07-27 23:29 UTC`——**开票要到 2026-07-27，四级审批（阈值/法定人数）路由的真实行为本轮完全没有被检验，属于样本不足，必须在开票后复采。**这是 `POLIS_POLICY_APPROVAL_ENABLED=true` 最大的未验证面。

---

## 7. ⚠️ P0 事故记录：2026-07-25 16:53 UTC 世界数据被清空，含 12 个玩家角色

> 本节应跨线情报要求单开。**查明原因不在本次任务范围，本节只留可追查的记录，未做任何补救性写操作。**

### 7.1 事实（全部只读取证）

事故前快照——来自 `/opt/skills-world/deploy/db-backup-roster-20260725-164629.sql.gz`（2026-07-25 16:46 UTC，72 559 925 B）：

```
public.residents      26        （resident_type: player 12 / npc 14）
public.users          45        （其中 12 个 player_resident_id 非空）
public.conversations  20
public.messages      106
public.memories    27514
public.llm_usage   25354
```

事故后现状（2026-07-26 02:2x UTC 实测）：

```
 users_total | with_player_resident
-------------+----------------------
          45 |                    0

 resident_type | count          conversations | 0
---------------+-------         llm_usage     | 2419
 npc           |    11          memories      | 4873
```

**关键时间戳——live 库里最老的行是 2026-07-25 16:53:47**：

```
$ psql -c "select min(created_at), max(created_at) from residents;"
 2026-07-25 16:53:47.565493+00 | 2026-07-25 17:15:23.65689+00
$ psql -c "select min(created_at), max(created_at), count(*) from memories;"
 2026-07-25 16:53:47.861581+00 | 2026-07-26 02:28:24.684753+00 | 2925
```

即：**世界侧数据没有一行早于 2026-07-25 16:53:47**（= 16:46 备份之后 7 分钟、api 容器 `StartedAt 16:53:59` 之前 12 秒）。`users` 表是唯一幸存者，`created_at` 仍横跨 2026-07-07 → 2026-07-23，45 行完好。

丢失的 12 个玩家角色 slug（来自事故前备份，只列 slug，不含任何隐私字段）：

```
p-新居民, p-新居民-466207, p-新居民-8b6aa3, p-新居民-a55197, p-新居民-adc21f,
p-新居民-d7de95, p-新居民-d97d9c, p-新居民-ef4836, p-新居民-fb9b04,
p-测试员小柯, p-测试员小柯-0a8352, p-测试员小柯-1a106a
```

同时消失的 14 个旧 NPC：`adam, isabella, klaus, mei, tamara, 夏洛克-福尔摩斯, 夜风侦探, 夜风侦探-46ff1f, 夜风侦探-a23160, 林晚秋, 格蕾丝-霍珀, 部署回归图灵0724, 阿达-洛芙莱斯, 陈默`。

现存 11 个全部是新阵容：`a-lan, chen-tiesheng, gu-mingyuan, he-qiaoyun, jiang-lin, lin-wanqiu, luo-xiaozhou, shen-jingshu, su-xiaoman, zhao-qiwen, zhou-dahe`。

### 7.2 已排除的怀疑对象

**不是 999e098 的 `bootstrap` 服务干的。**该服务的容器 `deploy-bootstrap-1` 全量带时间戳日志只有两次运行，都在事故之后，且几乎什么都没删：

```
$ docker logs -t deploy-bootstrap-1 | grep -E "Removing|Seeded|No old"
2026-07-25T17:12:11.040645893Z No old built-in residents found.
2026-07-25T17:12:11.040796639Z Seeded 0 new residents. World now contains:
2026-07-25T17:15:23.819236584Z Removing old built-in residents:
2026-07-25T17:15:23.819296827Z Seeded 1 new residents. World now contains:
```

第一次运行（17:12:11）就已经看到"世界里只有那 11 个新居民"——**清空发生在它之前（16:53），不是它造成的**。第二次（17:15:23）只删了 `isabella` 一个。

**不是卷切换。**`deploy_pgdata` 创建于 2026-07-07T14:09:37Z 至今没换过，是 simverse 唯一的业务库卷；`deploy_postgres_data` 与 simverse 无关（见 §6 下面的 §7.4）。

**不是 `reset_builtin_residents` 的正常路径。**该脚本 `find_targets()` 的第一个条件就是 `Resident.resident_type != "player"`，按代码它删不掉 12 个 `player` 型居民。但事实是 12 个 player 全没了 + 45 个 `users.player_resident_id` 全被置空（后者恰恰是该脚本 `users.player_resident_id` 置空逻辑的特征）。**代码语义与实际结果对不上，这一点没有查清。**

### 7.3 未查明 / 需要 Jimmy 决策的

- 16:53:47 那一刻到底跑了什么，**没有留下任何痕迹**：`docker ps -a` 里没有相应的一次性容器（`docker compose run --rm` 会自删），`/root/.bash_history` 只有 1 行（agent 走非交互 ssh 不写 history）。
- **补救可能性：存在。**事故前的完好备份还在，两份：

| 备份 | 路径 | 大小 | 内容 |
|---|---|---|---|
| 事故前 26 分钟 | `/opt/skills-world/deploy/db-backup-roster-20260725-164629.sql.gz` | 72 559 925 B | residents 26（player 12 / npc 14）、users 45（12 个有 player 角色）、conversations 20、memories 27514、llm_usage 25354 |
| 事故前 ~1h20m | `/opt/skills-world/db-backup-25B-20260725-153022.sql.gz` | 71 982 419 B | 25B 部署前 |
| 事故后（本次） | `/opt/skills-world/db-backup-ops0726-20260726-021511.sql.gz` | 4 240 190 B | 当前状态 |

- **本线未做任何恢复尝试**——恢复是不可逆的生产写操作，且会覆盖 16:53 之后 9.5 小时的新世界数据（4873 条记忆、2419 条 llm_usage、3 个进行中的 poll），必须由 Jimmy 决定取舍。
- **建议的即时防护**：在原因查清之前，不要再跑任何会触发 `reset_builtin_residents` 的动作——包括 `docker compose up`（compose 里 `bootstrap` 是 api/agent-worker 的 `service_completed_successfully` 前置，每次 `up` 都会跑一遍）。这也是本次 §4.2 选择"改 `.env` 不重启"的直接原因。

### 7.4 跨线情报的更正：`deploy_postgres_data` 不是 simverse 的数据

人口口径线报的"1.1G 孤立卷、已无任何容器挂载、可能是 07-25 之前的真实生产数据"——**这个判断不成立**，实测如下（全部只读）：

```
$ docker volume inspect deploy_postgres_data
  "CreatedAt": "2026-06-27T14:39:00Z",
  "Labels": {"com.docker.compose.project": "deploy",
             "com.docker.compose.volume": "postgres_data"}

$ docker ps -a --filter volume=deploy_postgres_data --format "{{.Names}}"
sub2api-postgres                       # ← 正在运行，不是孤立卷

$ docker inspect sub2api-postgres --format "running={{.State.Running}} project={{index .Config.Labels \"com.docker.compose.project\"}} workdir={{index .Config.Labels \"com.docker.compose.project.working_dir\"}}"
running=true project=sub2api workdir=/root/sub2api/deploy

$ cat /var/lib/docker/volumes/deploy_postgres_data/_data/PG_VERSION
18
$ cat /var/lib/docker/volumes/deploy_pgdata/_data/PG_VERSION
16
```

结论：
- `deploy_postgres_data` 是 **PostgreSQL 18** 集群，2026-06-27 初始化，**当前由 `sub2api-postgres`（`postgres:18-alpine`，第三方服务 sub2api）挂载并正在写入**（`postmaster.pid` 在、`pg_wal` 目录 mtime 是今天 02:23）。
- simverse 的库是 **PostgreSQL 16**（`pgvector/pgvector:pg16`），在 `deploy_pgdata`。两者版本都对不上，**`deploy_postgres_data` 里不可能是 simverse 的数据**。
- 名字撞车的原因：sub2api 的 compose 工作目录是 `/root/sub2api/deploy`，默认 project 名同样解析成 `deploy`，于是两个项目共用了 `deploy_*` 卷命名空间。这是个命名污染隐患，但不是数据事故。

| 卷 | 大小 | PG 版本 | 挂载者 | 是 simverse 数据吗 |
|---|---|---|---|---|
| `deploy_pgdata` | 187M | 16 | `deploy-db-1`（运行中） | ✅ 是，本次备份的就是它 |
| `deploy_postgres_data` | 1.1G | 18 | `sub2api-postgres`（运行中） | ❌ 否，第三方 sub2api 的库 |

- **`docker volume prune` 全程未执行，两个卷都未删除、未覆盖。**`deploy_postgres_data` 除了 `ls` 顶层目录和 `cat PG_VERSION` 之外没有任何读写。

---

## 8. 给 ROADMAP 的状态更新建议

**阶段 2 里"S1-5 / S2-5 未部署"这一格可以改写。**依据：

- 迁移 048（`town_treasuries`）、049（`policies`）已在生产 head，`alembic current = 049_add_policies (head)`。
- 三个开关生产实际取值均为 `true`，`policies` 表已种子化 17 行、`town_treasuries` 已有 `town` 行，运行时探针确认 `settings.town_treasury_enabled / polis_policy_enabled / polis_policy_approval_enabled` 全 True。
- 已稳跑 9.5h，零重启、零 ERROR。

建议改写成（而不是简单打勾）：

> **S1-5 / S2-5：已部署 vm212 并已开闸**（2026-07-25 17:12 UTC，alembic 049）。
> 未完成的验证：①四级审批路由的真实行为要等 2026-07-27 23:29 UTC 三个 poll 开票后才有样本；②镇财政税入至今为 0（余额 0，`updated_at` 未变），需跨锚点复采；③`TOWN_WAGE_UNFUNDED_POLICY` 仍是过渡值 `mint`，待镇财政有存量后收紧到 `skip`。

**工程健康批（R3 / R4 / P2）建议单独标注为"已部署，部分验证"**：

> R3 夜间补跑：**生产实证生效**（2026-07-25 15:32 补回了被部署窗口吞掉的一天）。
> P2 五 loop 心跳：**生产实证生效**，`/health/loops` 五路全绿零误报；但"loop 真死了会告警"未被检验。
> R4 socializing 回收：**已上线在跑，未触发**（当前 0 个 socializing 居民，无样本），零误杀。

**另外建议在 ROADMAP 上新增一条 P0**：§7 的数据事故（12 个玩家角色 + 全部对话/记忆被清空，原因未明，事故前备份尚在）。这件事的优先级高于任何功能推进。

---

## 9. 本次改动的文件

| 文件 | 改动 |
|---|---|
| `deploy/backend/.env.example` | +63 行，登记 S1-5 / S2-5 / R4 / P2 共 18 个旋钮（值取保守默认） |
| `docs/reports/ops-deploy-2026-07-26-report.md` | 本报告（新增） |

生产侧：`/opt/skills-world/deploy/.env` 追加 7 行工程健康批旋钮（已备份，未重启容器）。

未触碰：任何后端代码、`docs/ROADMAP.md`、`backend/skills_world_dev.db`、形象线的一切资源（`media_static` 卷、`resident-sprite-worker`）、两个 postgres 卷。
