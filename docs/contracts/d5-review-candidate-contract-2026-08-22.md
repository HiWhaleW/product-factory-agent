# D5 AI PM → Reviewer → G1 确定性协作契约

> 状态：2026-08-22 后端契约已实现并通过 PostgreSQL 在线测试；隔离 fixture 的真实 AI PM / Reviewer 已消费该契约并打开 G1。G1 未代批，真实产品项目仍在 G0；本文不代表完整 D5 已通过。

## 1. 已实现的数据边界

新增表：

- `definition_submissions`：绑定 AI PM Run、Context Pack、博查结果哈希、Evidence Index/MRD 精确版本和 Reviewer Pack。
- `definition_reviews`：绑定 Reviewer Run、Red Team Review 精确版本、verdict 和可选 G1。

AI PM 与 Reviewer 的模型输出都是不可信提案。只有本契约的确定性服务可以写 ArtifactVersion、创建 Reviewer Pack 或打开 G1。LangGraph、Prompt 和 PermissionRequest 均不能推进项目状态。

## 2. AI PM 提交

`POST /api/v1/projects/{project_id}/definition-submissions`

请求头：`Idempotency-Key: <8-200 字符>`。

请求体使用 `DefinitionSubmissionCreate`，包含：

- `source_run_id / context_pack_id / expected_context_version`。
- 完整标准化博查 `research_results` 和对应 `evidence_set_hash`。
- 精确一个 `evidence_index` 和一个 `mrd` 提案；每个提案包含 title、Markdown content、EvidenceRef、assumptions 和 `waiting_review` 状态。

确定性检查：

1. Project 必须仍为 `mrd`，ContextVersion 必须是当前版本。
2. Run 必须为 `succeeded` 的 `ai-pm` Run，并精确绑定本次 Context Pack。
3. Run 必须有完整的 `model → checkpoint` Journal。
4. 博查必须有独立 Permission `allow`；PermissionRequest 不是 G0/G1。
5. 已确认 Tool Step 的 `evidence-set://<sha256>` 必须与提交的完整标准化博查结果一致。
6. 每个 EvidenceRef 必须等于 `bocha:web:<sha256(url)>`，提案不得引用结果集之外的证据。
7. 内容必须通过长度、Secret 样文本和 Artifact Store 安全检查。
8. 同一项目幂等键重放返回原结果；输入变化返回冲突；同一 Run 不可重复收费或重复提交。

成功后：

- 两个 ArtifactVersion 保持业务 `approval_status=draft`。
- `DefinitionSubmission.status=waiting_reviewer` 表示已通过确定性来源/内容检查、只可供 Reviewer 读取；它不等于用户批准。
- 创建 `definition-review/v1` Reviewer Context Pack。Pack 的普通事实只含已批准 Project Brief；待审 Artifact 通过独立 `review_candidates` 通道精确加载，避免把 draft 冒充 approved。
- 事件：`artifact.created|versioned`、`context.pack_created`、Reviewer 首次 `agent.joined`、`definition.submitted`。

## 3. Reviewer 输入

`GET /api/v1/projects/{project_id}/definition-submissions/{submission_id}/reviewer-input`

稳定返回 `DefinitionReviewerInputRead`：

- Project / ContextVersion / Submission / Reviewer Pack ID。
- Evidence Index 与 MRD 的精确 Artifact ID、版本、kind、内容哈希和已校验 UTF-8 内容。
- 本次允许引用的 EvidenceRef。
- Reviewer 任务和禁止动作。

Agent Runtime 的 `definition-review/v1` 加载规则与此接口一致：普通 `approved_materials` 和只读 `review_candidates` 分开；不传 AI PM message、自评、隐藏思维链、整段群聊或 Key。

## 4. Reviewer 提交与 G1

`POST /api/v1/projects/{project_id}/definition-submissions/{submission_id}/review`

请求体使用 `DefinitionReviewCreate`：精确 Reviewer Run/Pack/Context、`pass | pass_with_known_issues | reject`、findings，以及精确一个 EvidenceRef 非空的 `red_team_review`。

确定性服务验证 Reviewer Run 的 Project/Agent/Context/Pack、`model → checkpoint` Journal、Artifact 内容和 EvidenceRef，然后持久化 Red Team Review：

- `reject`：`DefinitionSubmission.status=changes_requested`，不打开 G1。
- `pass` / `pass_with_known_issues`：只打开一个 G1，精确绑定 Evidence Index、MRD、Red Team Review 三个版本。
- 打开 G1 后项目仍为 `mrd`、ContextVersion 不变。
- 只有用户调用 `POST /api/v1/gates/{gate_id}/decisions` 且 `approve`，才把三个版本变成 `approved` 并进入 `prd`。

Gate 与 PermissionRequest 始终分离。

## 5. 幂等、并发与恢复

- AI PM 提交：项目级 PostgreSQL advisory lock + `project_id/idempotency_key` 唯一约束 + `source_run_id` 唯一约束。
- Reviewer 提交：项目级锁 + `submission_id` 唯一审查 + `source_run_id` 唯一约束。
- 双击并发只产生一组 Evidence/MRD、一条 DefinitionSubmission 和一个 Reviewer Pack。
- Reviewer 重放只产生一个 Red Team Review 和一个 G1。
- Event sequence 在同一项目内连续；消费者用 cursor 或 SSE `id=sequence` 恢复。

## 6. API 错误

统一错误信封继续携带 `code / message / user_message / retryable / request_id`，不回显搜索正文、模型正文或 Key。

| 错误码 | 条件 |
|---|---|
| `SOURCE_RUN_INVALID` | Run 不存在、未成功或 Agent/Project/Context 不匹配 |
| `SOURCE_RUN_JOURNAL_INVALID` | model/checkpoint Journal 不完整 |
| `RUN_CONTEXT_BINDING_INVALID` | Run 未精确绑定提交的 Context Pack |
| `RESEARCH_PERMISSION_NOT_CONFIRMED` | 博查缺少独立 allow 决定 |
| `EVIDENCE_SET_HASH_MISMATCH` | 请求中的博查结果与声明哈希不一致 |
| `EVIDENCE_SET_NOT_CONFIRMED` | Run Tool Step 未确认该 evidence-set |
| `SENSITIVE_INPUT_REJECTED` | 产物中疑似包含密钥 |
| `REVIEW_CONTEXT_MISMATCH` | Reviewer 未使用该 Submission 的 Pack |
| `REVIEW_EVIDENCE_MISMATCH` | Reviewer 引用本次证据集之外的博查证据 |
| `DEFINITION_REVIEW_CONFLICT` | 同一 Submission 已有不同结果 |

## 7. 数据库迁移与测试

- Alembic：`20260822_0004`。
- 已在线验证：`0003 → 0004 → 0003 → 0004`。
- `pnpm test:api:integration`：42/42 通过。
- 新增测试覆盖：AI PM 提交、Permission 缺失拒绝、Artifact 安全写入、双击并发、重复提交、Reviewer 输入、Reviewer 重放、G1 只开一次、项目不被自动推进、cursor 连续恢复。
- `pnpm check` 通过；保留现有 Starlette/httpx 弃用警告。

## 8. 真实 Runtime 验证与尚未完成

- 最新隔离 AI PM Run `c64d328c…` 经 Permission/checkpoint 恢复、1 次博查与 1 次有界 schema retry 后成功；DefinitionSubmission 落下 Evidence/MRD v1。
- 最新隔离 Reviewer Run `daa10b4d…` 经 1 次 schema retry 后返回 `pass_with_known_issues`，Red Team Review v1 已持久，G1 `e30b1bb0…` 已打开但未决定。
- 失败模型尝试保留在 Run Journal；没有放宽 Schema 或使用 mock 继续。脱敏证据见 [`d5-ai-pm-research-smoke-2026-08-22.json`](../evidence/d5-ai-pm-research-smoke-2026-08-22.json)。
- 真实产品项目仍在 G0 等待用户决定；不得用测试 fixture 代批。
- 真实 G1 用户决定、来源质量人工评审、博查 429/账单和完整 AG-UI 长连接仍未验证。
- Builder、PRD、MVP、内测、部署不属于本次完成范围。
