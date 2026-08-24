# D5 博查 Web Research / Agent Runtime 后端对接契约

> 状态：2026-08-22 已按当前代码、真实博查和隔离 AI PM→Reviewer→G1 open 纵向冒烟核验。本文是后端、Agent Runtime 和前端消费方的同步边界；不代表真实产品 G0/G1、Builder 或完整 D5 已完成。

## 1. 配置与密钥边界

| 项 | 当前值 | 说明 |
|---|---|---|
| Provider | `bocha` | D5 唯一公开检索 Provider |
| 外部接口 | `POST https://api.bochaai.com/v1/web-search` | 仅允许官方 HTTPS Host |
| SecretRef | `BOCHA_API_KEY` | 本地 `.env` / 进程环境注入；只传引用名，不传原值 |
| Base URL 配置 | `WEB_RESEARCH_BASE_URL=https://api.bochaai.com/v1` | URL 不允许用户名、密码、Query 或 Fragment |
| SecretRef 配置 | `WEB_RESEARCH_API_KEY_REF=BOCHA_API_KEY` | D5 只接受此引用名 |
| 默认超时 | `WEB_RESEARCH_TIMEOUT_SECONDS=30` | 允许 1–120 秒；不发送给 Provider |

Key 只能进入服务端请求头 `Authorization: Bearer <secret>`。禁止进入仓库、前端、Prompt、Context Pack、群聊、Event、DAG、Artifact、Run/Step、日志、快照和错误正文。

## 2. 博查外部请求

请求头：

```http
Content-Type: application/json
Authorization: Bearer <由 BOCHA_API_KEY SecretRef 解析>
```

请求体：

| 字段 | 类型 | 必填 | 当前边界 / 默认值 |
|---|---|---:|---|
| `query` | string | 是 | 去首尾空白后 1–2000 字符 |
| `freshness` | enum | 否 | `noLimit`；可选 `oneDay`、`oneWeek`、`oneMonth`、`oneYear` |
| `summary` | boolean | 否 | `true` |
| `count` | integer | 否 | `10`，允许 1–50 |

Runtime 在 AI PM / `mrd` / `CAP-02` 路径中当前使用 `count=10`、`freshness=noLimit`、`summary=true`。输入首行若为 `Research query: <query>`，只将该明确查询发给博查，后续任务指令仍只供模型使用；未提供前缀时兼容使用完整输入。PermissionRequest 绑定实际查询的 SHA-256。它不会把 Key、整段群聊或隐藏思维链放入请求。

## 3. Provider 返回与内部标准化返回

博查成功响应由 Adapter 读取下列 Provider 字段：

```json
{
  "code": 200,
  "log_id": "provider request id",
  "data": {
    "queryContext": { "originalQuery": "..." },
    "webPages": {
      "totalEstimatedMatches": 0,
      "value": [
        {
          "name": "...",
          "url": "https://...",
          "siteName": "...",
          "snippet": "...",
          "summary": "...",
          "datePublished": "..."
        }
      ]
    }
  }
}
```

Adapter 对 Runtime 返回严格标准化对象：

| 字段 | 类型 | 来源 / 约束 |
|---|---|---|
| `provider` | `"bocha"` | 固定值 |
| `provider_request_id` | string \| null | `x-request-id`，否则 `log_id` / `request_id`；最多 200 字符 |
| `query` | string | `queryContext.originalQuery`，缺失时回退到本次查询 |
| `total_estimated_matches` | integer \| null | 非负数 |
| `results` | array | 严格结果数组 |
| `results[].evidence_ref` | string | `bocha:web:<sha256(url)>`，同 URL 稳定 |
| `results[].title` | string | Provider `name`；1–1000 字符 |
| `results[].url` | string | 仅接受带 Host 的 HTTP(S) URL |
| `results[].site_name` | string \| null | Provider `siteName` |
| `results[].snippet` | string \| null | Provider `snippet` |
| `results[].summary` | string \| null | Provider `summary` |
| `results[].date_published` | string \| null | Provider `datePublished` |

真实冒烟未观察到 Token 或费用字段，内部标准化响应也不承诺这两个字段；费用需要在 Provider 控制台或后续独立账单对账能力中核验。

## 4. Agent Runtime 内部 HTTP 接口

### 4.1 启动 Run

`POST /api/v1/agent-runtime/runs`

```json
{
  "context_pack_id": "已批准且与项目当前版本精确绑定的 Context Pack ID",
  "user_input": "本次任务输入，1–50000 字符"
}
```

AI PM 的公开搜索是 `billable`，Tool Policy 必须先返回 `ask`。首次响应应为 `state=waiting_human`，并返回 `permission_request_id`、`permission_input_hash` 和 `checkpoint_hash`；此时尚未调用博查或 DeepSeek。

### 4.2 决定 PermissionRequest

`POST /api/v1/permissions/{permission_id}/decisions`

```json
{
  "decision": "allow",
  "input_hash": "启动 Run 返回的 64 位 permission_input_hash",
  "decided_by": "local-admin"
}
```

`decision` 只能为 `allow` 或 `deny`。返回：

```json
{
  "permission_id": "...",
  "decision": "allow",
  "idempotent": false
}
```

Permission 只批准一次工具调用，不是 G0/G1 产品 Gate，也不得触发项目业务状态转移。

### 4.3 从 checkpoint 恢复

`POST /api/v1/agent-runtime/runs/{run_id}/resume`

无请求体。Runtime 先核验当前 Context、Permission 决定、checkpoint 内容哈希，以及未确认外部副作用的幂等键；通过后才执行 `web_research → model → checkpoint`。注意不要误用通用控制面接口 `POST /api/v1/runs/{run_id}/resume`。

### 4.4 RuntimeExecutionResult

```json
{
  "run_id": "...",
  "task_id": "...",
  "state": "waiting_human | succeeded | failed",
  "turns_used": 0,
  "retries_used": 0,
  "research_retries_used": 0,
  "tool_calls_used": 0,
  "requested_model": "deepseek-chat",
  "observed_model": null,
  "usage": {},
  "output": null,
  "tool_results": [],
  "error_code": null,
  "permission_request_id": null,
  "permission_input_hash": null,
  "checkpoint_hash": "..."
}
```

`tool_results` 只在 Runtime 的受控 checkpoint / 模型输入内使用。持久化 `RunStep.output_ref` 仅记录 `evidence-set://<sha256>`，不保存搜索全文。Agent 输出仍是不可信提案，必须交给确定性后端服务校验并持久化 Artifact/Version/Gate；LangGraph 不直接修改业务状态。

## 5. 恢复与事件消费

| 接口 | 用途 |
|---|---|
| `GET /api/v1/runs/{run_id}` | 读取 Run 与有序 Step Journal |
| `GET /api/v1/projects/{project_id}/permissions?status=open` | 读取待决定 PermissionRequest |
| `GET /api/v1/projects/{project_id}/events?cursor={sequence}` | cursor 短轮询恢复；响应头 `X-Event-Cursor` |
| `GET /api/v1/projects/{project_id}/events/stream?cursor={sequence}` | SSE 快照重连基础；事件 `id` 等于 sequence |

相关事件：`run.started`、`permission.opened`、`permission.decided`、`run.waiting`、`run.completed`、`run.failed`。相关 Step 顺序：首次 `runtime_start → checkpoint`；批准恢复后追加 `tool → model → checkpoint`。`tool` Step 使用 `web_research:{run_id}:{attempt}` 幂等键，恢复前若发现未确认外部副作用，返回 `SIDE_EFFECT_RECONCILIATION_REQUIRED`。

## 6. 错误码

### 6.1 博查 Adapter

| 错误码 | 条件 | retryable |
|---|---|---:|
| `BOCHA_CONFIGURATION_ERROR` | 非官方 Host、非法 SecretRef、SecretRef 缺失、超时越界 | 否 |
| `BOCHA_AUTHENTICATION_ERROR` | HTTP / Provider code 401、403 | 否 |
| `BOCHA_RATE_LIMIT` | HTTP / Provider code 429；解析 `Retry-After` | 是 |
| `BOCHA_TIMEOUT` | 客户端连接/读取超时 | 是 |
| `BOCHA_SCHEMA_INVALID` | 查询/数量越界或 Provider 成功响应不符合严格 Schema | 否；Graph 可在预算内重试 |
| `BOCHA_PROVIDER_ERROR` | 网络错误、其他 HTTP 错误、Provider 业务错误 | 仅 HTTP 5xx 为是 |

Provider 错误正文、异常原文和 Key 不进入对外错误消息。

### 6.2 Runtime / Permission

| 错误码 | HTTP / 返回位置 | 处理 |
|---|---|---|
| `WEB_RESEARCH_ADAPTER_UNAVAILABLE` | HTTP 503 | fail closed，不生成 Evidence/MRD |
| `CHECKPOINT_UNAVAILABLE` / `CHECKPOINT_INVALID` | HTTP 503 | 交还用户/运维核验，不从空状态继续 |
| `RUN_NOT_FOUND` | Runtime HTTP 409；控制面查询 404 | 不重试错误 ID |
| `STALE_CONTEXT` | HTTP 409 | 使用当前批准 Context Pack 新建 Run |
| `PERMISSION_DECISION_REQUIRED` | HTTP 409 | 先决定 Permission |
| `SIDE_EFFECT_RECONCILIATION_REQUIRED` | HTTP 409 | 先按幂等键对账 |
| `SENSITIVE_INPUT_REJECTED` | HTTP 409 | 将密钥移到本地 SecretRef |
| `PERMISSION_NOT_FOUND` | HTTP 404 | 刷新权限列表 |
| `PERMISSION_NOT_OPEN` / `PERMISSION_EXPIRED` / `PERMISSION_INPUT_CHANGED` | HTTP 409 | 不复用旧决定 |
| `PERMISSION_DENIED` | HTTP 200 的 `RuntimeExecutionResult.error_code` | 停止 Tool 与模型调用 |
| `TOOL_BUDGET_EXCEEDED` / `MAX_TURNS_EXCEEDED` / `AGENT_RUN_TIMEOUT` | HTTP 200 的 `RuntimeExecutionResult.error_code` | `waiting_human`，不得 mock 继续 |
| `BOCHA_*` / `DEEPSEEK_*` | HTTP 200 的 `RuntimeExecutionResult.error_code` | 按有界 retry 后交还用户 |
| `REQUEST_VALIDATION_FAILED` | HTTP 422 | 修正字段 |
| `INTERNAL_ERROR` | HTTP 500 | 携带 `request_id` 查脱敏后端日志 |

统一错误信封：

```json
{
  "error": {
    "code": "...",
    "message": "安全错误消息",
    "user_message": "安全用户消息",
    "retryable": false,
    "request_id": "req_..."
  }
}
```

## 7. 真实冒烟结论

- 官方 Endpoint 认证与中国大陆网络：通过。
- 中文查询、严格 Schema：通过；288 ms，10 条结果。
- `title/url/site_name/snippet/summary/date_published`：均 10/10 非空。
- EvidenceRef：对返回 URL 本地重算，10/10 稳定。
- 真实 1 ms 客户端超时：20 ms 内以 `BOCHA_TIMEOUT` fail closed。
- 真实 429：未观察；未以请求洪泛制造。
- Token / 费用字段：响应契约中未观察。
- 脱敏原始证据：[`d5-bocha-smoke-2026-08-22.json`](../evidence/d5-bocha-smoke-2026-08-22.json)。

## 8. 确定性提交边界（2026-08-22 已实现）

Agent Runtime 完成 `Permission allow → 博查 → DeepSeek` 后，不直接写 Artifact、Gate 或 Project。它把完整标准化 `research_results`、`evidence_set_hash`、严格 Evidence/MRD 提案、Run ID 和 Context Pack ID 提交到：

`POST /api/v1/projects/{project_id}/definition-submissions`

控制面重新计算 evidence-set Hash，并与已确认的 `RunStep.output_ref=evidence-set://<sha256>` 对账；同时验证 Permission、Run/Context/Journal、EvidenceRef 与 Artifact 内容。通过后才持久化 Evidence/MRD，并创建 `definition-review/v1` Reviewer 输入。字段、错误码和 G1 边界见 [`d5-review-candidate-contract-2026-08-22.md`](./d5-review-candidate-contract-2026-08-22.md)。

## 9. 跨线对齐结果

- Agent Runtime 线负责博查调用、Permission/checkpoint、AI PM 和 Reviewer Run。
- 确定性后端线负责重新验证结果、写入 Artifact/DefinitionSubmission/DefinitionReview，并打开 G1。
- 最新隔离真实链路已通过：1 次博查；AI PM 和 Reviewer 各经过 1 次有界结构化重试后成功；Event sequence 连续到 26。
- G1 已打开但未决定，fixture 项目保持 `mrd`；这不是对真实产品 G0/G1 的批准。
- 脱敏证据：[`d5-ai-pm-research-smoke-2026-08-22.json`](../evidence/d5-ai-pm-research-smoke-2026-08-22.json)。
