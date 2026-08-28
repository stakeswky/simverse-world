# Living Loop P0 产品事件分类与隐私白名单

- 版本：1.0
- 日期：2026-08-28
- 状态：服务端强制合同
- 保留期：90 天

本文定义 Living Loop P0 唯一允许持久化的产品事件、属性和聚合用途。未列出的事件名、属性键、属性值或数据类型一律拒绝，而不是静默删除。产品与状态机总合同见 [LIVING_LOOP_P0_SPEC.md](LIVING_LOOP_P0_SPEC.md)。

## 1. 原则

1. 事件账本只回答 P0 漏斗问题，不保存行为正文或用户画像。
2. `occurred_at` 由服务端写入，是指标的权威时间；`client_occurred_at` 只帮助诊断迟到/重试事件。
3. `user_id` 只从 Bearer 认证上下文派生，客户端请求体中没有该字段。
4. 客户端只可提交七个白名单事件；三个权威业务事件只能由服务端事务写入。
5. 前端事件失败、超时或被限流不得阻断读取决策、确认选择、查看结果或导航。
6. P0 不引入第三方分析 SDK，也不把事件发送到外部服务。

## 2. 存储信封

每一行 `product_events` 使用以下字段：

| 字段 | 来源 | 约束 | 指标权威性 |
|---|---|---|---|
| `id` | 服务端 | UUID 主键 | 无业务含义 |
| `event_id` | 客户端或服务端 | 客户端 UUID4、服务端稳定 UUID5，全局唯一 | 重试幂等键；版本分区防止客户端预占服务端标识 |
| `user_id` | 认证上下文 | 非空、索引 | 用户去重键，不得返回管理指标 |
| `session_id` | 客户端可选 | UUID 或 `null`，最长 36 字符 | 仅诊断，不参与核心漏斗 |
| `event_name` | 事件生产者 | 本文十个枚举之一 | 漏斗分类 |
| `properties_json` | 事件生产者 | 逐事件白名单；对象；不允许额外键 | 仅本文指定用途 |
| `occurred_at` | 服务端 | UTC 接收时间或同事务业务时间 | 权威时间 |
| `client_occurred_at` | 客户端可选 | ISO 8601 UTC 或 `null` | 非权威 |
| `created_at` | 服务端 | UTC 持久化时间 | 运维与保留清理 |

服务端事件可以让 `occurred_at` 等于同事务中的 `choice_confirmed_at`、`result_settled_at` 或 `result_viewed_at`。客户端提供的时间不得影响状态、到期判断、48 小时回访率或管理漏斗。

## 3. 客户端批量 API

### 3.1 请求

`POST /product-events/batch` 要求 Bearer 认证和 `application/json`：

```json
{
  "events": [
    {
      "event_id": "52cecfca-265b-442b-a7ec-c2f5b487d571",
      "session_id": "66e32de4-2ba0-44d0-90ca-a1ca9f146dcf",
      "event_name": "living_loop_choice_previewed",
      "client_occurred_at": "2026-08-28T12:00:00Z",
      "properties": {
        "surface_version": 1,
        "decision_id": "afe0c239-bd26-401c-80cf-97d4fc9953bc",
        "scenario_key": "harbor_wage_dispute_v1",
        "scenario_version": 1,
        "choice_key": "private_mediation"
      }
    }
  ]
}
```

信封约束：

- `events` 必须有 `1..20` 项。
- 解压前原始请求体最多 `32768` bytes；超限返回 `413`。
- 单个事件对象只允许 `event_id`、`session_id`、`event_name`、`client_occurred_at`、`properties`。
- 客户端 `event_id` 必须是规范 UUID4 字符串；服务端权威事件使用稳定 UUID5，两个命名空间不得混用。`session_id` 若存在必须是规范 UUID 字符串。
- `client_occurred_at` 若存在必须带时区并可转换为 UTC；它不会覆盖服务端时间。
- `properties` 必须是对象，并与事件名对应的完整 schema 匹配。
- 使用现有 REST limiter，按实际客户端 IP 每分钟最多 30 个批量请求；超限返回 `429`。

### 3.2 验证和事务语义

批量采用“全批拒绝”合同：任何一项 schema 非法、含服务端事件名或包含禁用字段，整批返回 `422`，不写任何行。通过验证后整批在一个事务中持久化。

幂等规则：

- 新 `event_id` 写一行。
- 已存在且 `user_id`、`event_name`、`session_id` 和规范化属性完全一致时视为重试，不写第二行。
- 同一批内完全相同的重复事件只写一次，其余计入 `duplicates`。
- 同一 `event_id` 绑定到不同用户、事件名、会话或属性时整批返回 `409 idempotency_conflict`；响应不得暴露已有行属于谁。
- 并发插入依靠数据库唯一约束收敛；不能只在插入前查询。

成功响应固定为：

```json
{
  "accepted": 1,
  "duplicates": 0
}
```

`accepted + duplicates` 等于去除批内完全相同项前的请求事件数。响应不回显属性、用户或会话标识。

## 4. 通用枚举

本文所有字符串值区分大小写。除了固定值，不接受自定义文本。

| 类型 | 合法值 |
|---|---|
| `surface_version` | 整数 `1` |
| `scenario_key` | `harbor_wage_dispute_v1` |
| `scenario_version` | 整数 `1` |
| `choice_key` | `public_support \| private_mediation \| collect_evidence` |
| `decision_state` | `pending \| chosen \| result_ready \| result_viewed` |
| `entry_point` | `root \| direct \| return` |
| `town_source` | `header \| secondary \| fallback` |
| `pulse_source` | `card \| since_you_left` |
| `pulse_target` | `capsules` |

`decision_id` 是 UUID。不得用标题、居民名、Notification 文本、Digest 文本或延迟结果代替这些枚举。

## 5. 客户端允许事件

所有客户端事件是体验遥测，不是业务状态的证据。除表中键外，`properties` 不允许任何额外键。

### 5.1 `living_loop_today_viewed`

当且仅当启用的 `/today` 主内容成功渲染后发送；loading、error、feature-disabled 和 setup-required 不发送。

| 属性 | 类型 | 必填 | 合法值 |
|---|---|---:|---|
| `surface_version` | integer | 是 | `1` |
| `entry_point` | string | 是 | `root \| direct \| return` |

用于 `/today` 独立访问用户数。

### 5.2 `living_loop_decision_viewed`

当可交互决策卡首次出现在当前页面实例中时发送。刷新可形成新事件，但重试同一事件使用相同 `event_id`。

| 属性 | 类型 | 必填 | 合法值 |
|---|---|---:|---|
| `surface_version` | integer | 是 | `1` |
| `decision_id` | string | 是 | UUID |
| `scenario_key` | string | 是 | `harbor_wage_dispute_v1` |
| `scenario_version` | integer | 是 | `1` |
| `decision_state` | string | 是 | 通用状态枚举 |

用于看到决策的独立用户数和选择完成率分母。

### 5.3 `living_loop_choice_previewed`

用户选择一个选项、但尚未在二次确认中提交时发送。用户改变预览选项可以形成新事件。

| 属性 | 类型 | 必填 | 合法值 |
|---|---|---:|---|
| `surface_version` | integer | 是 | `1` |
| `decision_id` | string | 是 | UUID |
| `scenario_key` | string | 是 | `harbor_wage_dispute_v1` |
| `scenario_version` | integer | 是 | `1` |
| `choice_key` | string | 是 | 通用选项枚举 |

只用于选择交互诊断，不作为权威确认。

### 5.4 `living_loop_immediate_result_viewed`

服务端确认成功后，立即结果区域首次在当前页面实例中可见时发送。

| 属性 | 类型 | 必填 | 合法值 |
|---|---|---:|---|
| `surface_version` | integer | 是 | `1` |
| `decision_id` | string | 是 | UUID |
| `scenario_key` | string | 是 | `harbor_wage_dispute_v1` |
| `scenario_version` | integer | 是 | `1` |
| `choice_key` | string | 是 | 通用选项枚举 |

只用于 UI 送达诊断；不能替代 `living_loop_choice_confirmed`。

### 5.5 `living_loop_delayed_result_viewed`

延迟结果正文首次在当前页面实例中可见，且 result-viewed API 已成功或正在幂等重试时发送。

| 属性 | 类型 | 必填 | 合法值 |
|---|---|---:|---|
| `surface_version` | integer | 是 | `1` |
| `decision_id` | string | 是 | UUID |
| `scenario_key` | string | 是 | `harbor_wage_dispute_v1` |
| `scenario_version` | integer | 是 | `1` |
| `choice_key` | string | 是 | 通用选项枚举 |

只用于 UI 送达诊断；48 小时回访率使用服务端 first-viewed 事件。

### 5.6 `living_loop_enter_town_clicked`

用户从 `/today` 选择进入 `/play` 时发送。发送失败必须继续导航。

| 属性 | 类型 | 必填 | 合法值 |
|---|---|---:|---|
| `surface_version` | integer | 是 | `1` |
| `source` | string | 是 | `header \| secondary \| fallback` |

只用于 Today 到地图的导航诊断。

### 5.7 `living_loop_city_pulse_opened`

用户打开城市脉搏深链接时发送。发送失败必须继续导航。

| 属性 | 类型 | 必填 | 合法值 |
|---|---|---:|---|
| `surface_version` | integer | 是 | `1` |
| `source` | string | 是 | `card \| since_you_left` |
| `target` | string | 是 | `capsules` |

只用于城市脉搏入口诊断；不得保存 Digest 标题或摘要。

## 6. 仅服务端事件

以下事件不得出现在 `POST /product-events/batch`；客户端提交时整批返回 `422`。它们与对应业务状态在同一数据库事务写入。

### 6.1 共同属性

三个服务端事件的 `properties_json` 只允许：

| 属性 | 类型 | 合法值 |
|---|---|---|
| `decision_id` | string | UUID |
| `scenario_key` | string | `harbor_wage_dispute_v1` |
| `scenario_version` | integer | `1` |
| `choice_key` | string | 通用选项枚举 |

不保存立即影响数值、结果正文、居民资料或倒计时。

### 6.2 `living_loop_choice_confirmed`

- 与 `pending → chosen` 同事务。
- `occurred_at` 等于首次 `choice_confirmed_at`。
- 用户提供的选择 `idempotency_key` 可直接作为该事件的 `event_id`，从而持久化完整重试绑定。
- 同一 decision 后续相同选项请求不创建新确认事件。
- 用于确认用户数、完成率、决策耗时和选项分布。

### 6.3 `living_loop_result_settled`

- 与 `chosen → result_ready` 同事务。
- `occurred_at` 等于 `result_settled_at`。
- `event_id` 必须对 `(event_name, decision_id)` 稳定且唯一，或由等价数据库约束保证唯一。
- 用于到期/结算结果数量。

### 6.4 `living_loop_result_first_viewed`

- 与 `result_ready → result_viewed` 同事务。
- `occurred_at` 等于首次 `result_viewed_at`，重试不覆盖。
- `event_id` 必须对 `(event_name, decision_id)` 稳定且唯一，或由等价数据库约束保证唯一。
- 用于延迟结果查看用户数和 48 小时回访率。

## 7. 禁止数据

以下信息不得出现在 `session_id`、`properties_json`、事件名、错误详情或事件日志中：

- 聊天消息、提示词、记忆正文、Notification 正文、Digest 正文、场景或结果正文。
- 姓名、显示名、slug、邮箱、电话号码、地址或其他直接身份信息。
- Bearer Token、OAuth/JWT、Cookie、CSRF、API key、密码或任何秘密。
- IP、完整 User-Agent、设备指纹、精确位置或外部广告标识。
- 任意自由文本、任意 URL、referrer 查询字符串或前端堆栈。
- Soul Coin 余额、关系详情、Challenge session/capability 或其他非 P0 业务状态。

`decision_id`、枚举场景/选项和随机 `session_id` 是 P0 必需的受限假名标识。它们只能用于本文列出的聚合与幂等，不得扩展为用户画像。

## 8. 保留和清理

- `product_events` 从 `created_at` 起保留 90 天。
- `living_loop_days` 是用户选择的产品记录，不受产品事件 90 天清理影响。
- P0 提供手动清理脚本 `backend/scripts/cleanup_product_events.py`。
- 从 `backend/` 运行 dry-run：

  ```bash
  python3 scripts/cleanup_product_events.py --retention-days 90
  ```

- 只有显式 `--apply` 才删除：

  ```bash
  python3 scripts/cleanup_product_events.py --retention-days 90 --apply
  ```

- cutoff 以服务端 UTC `created_at < now - 90 days` 计算；边界相等的行保留。
- dry-run 和 apply 只输出 cutoff、候选/删除总数，不输出用户、会话、属性或事件正文。
- P0 不注册常驻清理任务；调度自动化需要另行安全评审。

## 9. 指标映射

| 管理指标 | 权威来源 | 说明 |
|---|---|---|
| Today 独立用户 | `living_loop_today_viewed` | 窗口内按服务端 `occurred_at` 去重 user |
| 决策查看独立用户 | `living_loop_decision_viewed` | 完成率分母 |
| 确认独立用户 | `living_loop_choice_confirmed` | 不能用立即结果客户端事件替代 |
| 选择完成率 | 决策查看 + 确认 | 分母为零返回 `null` |
| 到期结果数 | `living_loop_result_settled` | 按 decision 计数，非用户数 |
| 延迟结果查看用户 | `living_loop_result_first_viewed` | 不能用客户端 delayed-viewed 替代 |
| 48 小时回访率 | choice confirmed + first viewed + decision timestamps | 采用主规格的完整观察窗口定义 |
| 中位决策时间 | `living_loop_days.first_viewed_at` → `choice_confirmed_at` | 仅非负权威时间差 |
| 选项分布 | 服务端 confirmed 的 `choice_key` | 只返回三个固定桶 |

管理响应只返回聚合结果，不返回 event/user/session/decision ID 或单行数据。

## 10. 验收清单

实现必须用自动测试证明：

1. 七个客户端事件及其每个合法枚举被接受。
2. 三个服务端事件、未知事件、额外属性、自由文本和错误类型被拒绝。
3. 0 条、21 条、超过 32 KiB 和超过速率的请求分别失败且不写数据。
4. 一项非法导致全批不写；事务中途失败也不产生部分批次。
5. 相同 `event_id` 精确重试不重复；冲突绑定返回 `409`；并发写只留一行。
6. `user_id`、`occurred_at` 由服务端派生，客户端无法覆盖。
7. 事件发送失败不阻断选择、result-viewed 或页面导航。
8. 管理漏斗只用指定权威来源且不返回 PII。
9. 清理脚本默认 dry-run，`--apply` 只删除 cutoff 之前的产品事件。
10. 日志和 API 响应不回显批量属性、秘密或尚未到期的延迟正文。
