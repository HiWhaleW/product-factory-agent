# D5 真实 Agent Runtime 进度与问题台账

> 日期：2026-08-22  
> 当前结论：销售复盘 Agent 虚拟产品已真实跑通 G1，并由用户批准进入 `prd / Context v3`。首轮 Reviewer `reject` 后系统 fail-closed；修订 Evidence/MRD v2 后 Reviewer 以 `pass_with_known_issues` 通过。PRD Context Pack 已创建，Builder 未启动。

## 已完成

- 完整读取项目级 `AGENTS.md`、D5 编排/Context/State-Gates/Capability/Tool Policy/Harness/验收规格及 4 个冻结 Prompt；未修改冻结 Prompt、Agent 数量、职责或技术栈。
- 实现 fail-closed DeepSeek Adapter：本地 SecretRef、普通响应、SSE、Tool Calls、JSON mode + 本地 Pydantic Schema，以及认证/限流/超时/context-too-long/Provider/Schema/Tool 类型化错误。
- 实现 4 Agent 冻结注册表。D5 激活 Factory Lead、AI PM、Reviewer；Builder 只注册，运行请求被拒绝。
- 实现有界 LangGraph `model → policy → finish` 图：`max_turns`、有限 Schema/超时/429 重试、超时、结构化输出校验和 `allow/ask/deny` Tool Policy。
- 实现 LangGraph 原生 `interrupt` 暂停/继续；最新 checkpoint 序列化到受控 `ARTIFACT_ROOT/.runtime-checkpoints`，SHA-256 记入 PostgreSQL `RunStep`，可在新 Service/新 `InMemorySaver` 恢复。
- 实现 Run/Step Journal：`runtime_start`、每次模型尝试的 `model`、`checkpoint`。恢复前检查未知外部副作用，幂等键尚未对账时返回 `SIDE_EFFECT_RECONCILIATION_REQUIRED`。
- Runtime 只创建 Task/Run/RunStep/Event，不批准 Gate，不推进项目业务状态；输出事件可持久化并通过 cursor 恢复。
- Agent 套件 33/33 通过；PostgreSQL 全套集成测试 42/42 通过；migration 为 `20260822_0004 (head)`。最终 `pnpm check` 结果见本文末次验证记录。
- 本台账、博查进度、根 README 和 handoff HTML 已使用真实浏览器检查 `1440×900` / `390×844`，均无页面级横向溢出；该结果不代表产品 Web 视觉验收。

## DeepSeek 真实冒烟

| 项目 | 结果 | 脱敏证据摘要 |
|---|---|---|
| 渠道/认证/网络 | 通过 | 中国大陆官方 `https://api.deepseek.com`；Key 仅通过 `DEEPSEEK_API_KEY` SecretRef 注入 |
| 模型 | 已观察 | 请求 `deepseek-chat`；服务端响应 `deepseek-v4-flash` |
| SSE 流式 | 通过 | 返回多个 delta |
| 工具调用 | 通过 | 强制函数调用返回符合声明的 JSON object |
| JSON/Schema | 通过 | JSON mode 输出通过 `extra=forbid` 本地 Schema 校验 |
| 中文长文档 | 通过 | 13,391 字输入；仅保存哈希、长度和 Token 指标 |
| 超时 | 通过 | 真实 1 ms deadline 分类为 `DEEPSEEK_TIMEOUT` |
| context-too-long | 通过 | 约 1,050,044 Token 被 Provider 拒绝并分类为 `DEEPSEEK_CONTEXT_TOO_LONG` |
| Token/费用 | 部分 | Provider 返回 Token；未返回费用字段，Runtime 不伪造费用 |
| 真实 HTTP 429 | 未观察 | 未使用请求洪泛制造限流；429/`Retry-After` 分类与有限重试只有单测证据 |

完整 Provider 证据：[`d5-deepseek-smoke-2026-08-22.json`](./d5-deepseek-smoke-2026-08-22.json)。

## 真实 Agent Runtime 证据

- Factory Lead Run `31b66776-37aa-4392-838f-109436f147f5`：成功，1 turn，0 retry，2,761 Token，观察模型 `deepseek-v4-flash`。
- Reviewer Run `63f6db0b-5e98-4f3f-adef-f2f5a6a1b2ac`：成功，1 turn，0 retry，2,067 Token，观察模型 `deepseek-v4-flash`。
- 两个 Run 均持久化 `runtime_start → model → checkpoint`；证据保存输出 SHA-256 与 checkpoint SHA-256，不保存 Prompt 或模型输出正文。
- cursor 证据包含 4 个 Run 事件，最后 sequence 为 17。
- 前一次成功 AI PM Run `9847aaf8-d6fe-4fee-a218-96b58d176623`：`waiting_human → Permission allow → checkpoint resume → 1 次博查 → 3 次有界模型尝试 → succeeded`，其中 2 次 Schema 失败有记录但不保存失败正文。共 13,544 Token，10 个 EvidenceRef。
- AI PM Journal：`runtime_start → checkpoint → tool → model(failed) → model(failed) → model(completed) → checkpoint`；Tool 幂等键已确认，evidence-set Hash 与 DefinitionSubmission 提交值一致。
- DefinitionSubmission `da6fe1c1-2307-446e-96e0-b79f82b80ebc` 原子持久 Evidence Index/MRD v1，两者仍为 `draft`，并创建 `definition-review/v1` Reviewer Pack。
- Reviewer Run `5e91b4c1-de1f-459c-851f-a47ecadbc975`：2 turns / 1 schema retry / 0 tools / 13,412 Token，输出 `pass_with_known_issues`。Red Team Review v1 落库后打开 G1 `fb894599-1df1-424c-ae56-04d48395bd52`；G1 仍为 `open`，项目未进入 PRD。
- 失败历史被保留：一次真实 Reviewer `reject` 正确进入 `changes_requested`；三个 AI PM Run 在 3 次尝试后以 `DEEPSEEK_SCHEMA_INVALID` 交还用户、且未持久 Artifact。

完整 Runtime 证据：[`d5-runtime-smoke-2026-08-22.json`](./d5-runtime-smoke-2026-08-22.json)。

### 末次隔离复跑与验证

- 最新隔离 AI PM Run `c64d328c…`：1 次博查、1 次 schema retry、10 个 EvidenceRef，最终成功。
- 最新隔离 Reviewer Run `daa10b4d…`：0 tools、1 次 schema retry，最终 `pass_with_known_issues`。
- Red Team Review 已落库；G1 `e30b1bb0…` 为 `open`、未决定；fixture 项目仍为 `mrd`；Event sequence 连续到 26。
- `pnpm check`：Web 6/6、Python 54/54；42 项在线测试在普通检查中按设计跳过。
- `pnpm test:api:integration`：允许访问本机 PostgreSQL 后 42/42 通过。
- Alembic：`20260822_0004 (head)`。
- 保留 1 条 `StarletteDeprecationWarning`。第一次在受限环境运行在线测试出现 31 failed / 40 errors，根因均为系统禁止访问 `127.0.0.1:5432`；按允许方式重跑后全部通过，没有隐藏该失败。
- 最新脱敏证据：[`d5-ai-pm-research-smoke-2026-08-22.json`](./d5-ai-pm-research-smoke-2026-08-22.json)。

## Context Pack 内容边界

- 只接收当前 Project/Context/Stage 匹配且 `approved` 的确定性 Context Pack 和精确版本引用。
- 模型可见：Pack ID/项目/版本/阶段/接收 Agent、任务、Capability/禁止动作/预算、已批准 Project Brief/产物。Reviewer 额外只读取该 DefinitionSubmission 精确绑定的两个 `review_candidates`，它们明确标记为 `draft/waiting_reviewer`，不冒充 approved material。
- 模型不可见：整段群聊、隐藏思维链、无关草稿/产物、Secret 原值。证据不保存 Prompt、搜索正文或模型正文。

## 销售复盘 Agent 虚拟产品真实复跑

- 项目 `2a3c38e1…` 的 G0 `b242ef80…` 已由用户批准；AI PM Context Pack 为 `33554516…`。
- 首轮 AI PM `d07c8a13…` 使用 1 次博查、1 turn、10,367 Token；Reviewer `9b419c47…` 返回 `reject`，提交进入 `changes_requested`，G1 未打开。
- 根因是公开搜索查询混入长任务指令，且证据与销售复盘直接关联度不足。Runtime 已改为支持首行 `Research query:`：博查只接收明确查询，后续指令只供模型使用；PermissionRequest 绑定实际查询 Hash。
- 修订 AI PM `0df21c90…` 成功并生成 Evidence Index/MRD v2。首次 Reviewer `f5321d65…` 因 `DEEPSEEK_PROVIDER_ERROR` 交还用户，未开 G1；新 Reviewer Run `d6b2444e…` 不使用工具、1 turn、8,786 Token，返回 `pass_with_known_issues`。
- Red Team Review v2 已落库；G1 `cec40b01…` 已由用户批准。确定性控制面依次产生 `context.updated → gate.decided → project.state_changed → context.pack_created`，Event sequence 连续到 63。项目为 `prd / Context v3`，PRD Context Pack `7e918f18…` 精确绑定 MRD v2、Evidence Index v2 和 Red Team Review v2。两项 P2 已知问题继续保留。
- 脱敏证据：[`d5-sales-retrospective-product-flow-2026-08-22.json`](./d5-sales-retrospective-product-flow-2026-08-22.json)。

## 未完成、失败与 fail-closed 项

1. G1 已由用户批准，项目已进入 PRD；PRD Agent Run、确定性 PRD 持久化和 G2 尚未执行。
2. 博查真实中文搜索、严格 Schema、稳定 EvidenceRef 与短超时已通过；真实 429、账单/费用字段和来源质量人工评审仍未完成。详见 [`d5-bocha-adapter-progress-2026-08-22.html`](./d5-bocha-adapter-progress-2026-08-22.html)。
3. 产品 Reviewer 已真实运行并返回 `pass_with_known_issues`；G1 批准不表示两项 P2 风险已消失。
4. Tool Policy 可产生 PermissionRequest，但尚未注册的工具 Adapter 会返回 `TOOL_ADAPTER_UNAVAILABLE`，不会用 mock 继续。
5. Builder 仅注册且 D5 禁用；Codex CLI 仍仅有只读版本检查。本轮不宣称 Builder、MVP、内部验收、种子用户内测或发布完成。

## 本轮最终验证

- `pnpm check`：ESLint、TypeScript、Web 6/6、Ruff、Python 54 passed；PostgreSQL 42 项按设计在该命令中 skip。
- `pnpm test:api:integration`：真实 PostgreSQL 42/42；Alembic 当前 `20260822_0004 (head)`。
- ego-browser 重新预览本 HTML 与 AI PM→Reviewer→G1 契约 HTML；`1440×900` 和 `390×844` 均为页面水平溢出 0。
- 保留 Starlette `TestClient` / `httpx` 弃用警告，未降低验收或隐藏。

## 并行任务对齐

- 后端线：保持 Gate/Project 状态转移为确定性服务；Runtime 仅消费已批准 Context Pack 并持久化 Run/Step/Event。项目创建的启动事件契约为 `project.created → agent.joined → context.pack_created`，后续事件序号必须连续。
- 已同步契约：[博查](../contracts/d5-bocha-web-research-contract-2026-08-22.md) 和 [AI PM→Reviewer→G1](../contracts/d5-review-candidate-contract-2026-08-22.md)。后端的 DefinitionSubmission/Review 契约已被真实 Runtime 消费；后续仍需保持 LangGraph 不直接修改业务状态。
- 前端线：本开发线未修改 `apps/web/**`。可消费 Runtime 的 cursor Event，但完整 AG-UI 长连接和恢复交互仍未验收。
