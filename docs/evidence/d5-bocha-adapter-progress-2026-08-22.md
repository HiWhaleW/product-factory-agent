# D5 博查 Web Research Adapter 进度证据

> 日期：2026-08-22  
> 结论：博查官方 API 契约、fail-closed Adapter 和 LangGraph Tool 路径已实现；`BOCHA_API_KEY` 已通过本地 SecretRef 注入。最新隔离 fixture 已真实贯通博查、AI PM、Evidence/MRD 落库、Reviewer、Red Team Review 和 G1 open；G1 未决定，真实产品仍在 G0。

## 已锁定的非密钥契约

| 项目 | 值 |
|---|---|
| 渠道 | 博查 AI 开放平台官方 Web Search API |
| Endpoint | `POST https://api.bochaai.com/v1/web-search` |
| 认证 | `Authorization: Bearer <SecretRef>` |
| SecretRef | `BOCHA_API_KEY` |
| 默认超时 | 30 秒，允许范围 1–120 秒 |
| 默认请求 | `summary=true`、`count=10`、`freshness=noLimit` |

官方页面在 2026-08-22 可访问，并明示上述 Endpoint、Bearer 认证以及 `query/freshness/summary/count` 请求字段。

## 已实现

- `apps/api/app/adapters/bocha.py`：
  - 仅允许 `https://api.bochaai.com`，防止通过伪造 Base URL 外泄 Bearer Key。
  - Key 只通过 `BOCHA_API_KEY` SecretRef 解析，不进入 Settings 序列化、Prompt、Context Pack、Event 或错误正文。
  - 支持博查带 `code/data` 包装和直接 `SearchResponse` 两类响应包。
  - 输出限定为标题、URL、站点、snippet、summary、发布时间和稳定 `bocha:web:<sha256(url)>` EvidenceRef。
  - 认证、429、超时、Provider 和 Schema 错误全部类型化，不回显 Provider 错误 body 或 Key。
- LangGraph Agent Run：
  - AI PM + MRD + `CAP-02` 会进入 `research_policy → research → model`；其他 Agent/阶段不触发搜索。
  - `web_research` 是可计费外部调用，Tool Policy 输出 `ask`，生成独立 PermissionRequest；它不是 G0/G1。
  - 用户拒绝 Permission 时不会调用博查或 DeepSeek。
  - 用户允许后，可从持久化 checkpoint 在新 Service 恢复，执行 `tool → model → checkpoint`。
  - 超时/429/Schema 只做预算内有限重试；未知计费副作用未对账时拒绝恢复。
  - RunStep 只记录 Evidence 集合 SHA-256 引用，不在 Event 中嵌入搜索全文或 Key。

## 自动化证据

- 博查 Adapter 单测 6/6：缺 SecretRef/非官方域名拒绝、Bearer 与 EvidenceRef、两类响应包、认证脱敏、超时/429/Schema、输入边界。
- Agent 契约测试 24/24，包括 Permission `ask`、拒绝不调用、允许后搜索、有限重试和 MRD 阶段语义 Schema。
- Runtime PostgreSQL 子集和完整在线套件均通过，新增跨 Service 恢复后持久化 `tool/model/checkpoint` Journal。
- `pnpm test:api:integration`：42/42 通过。
- `pnpm check`：Web 6/6，Python 52 项通过；在线 PostgreSQL 42 项按设计在普通检查中跳过；ESLint、TypeScript、Ruff 通过。
- 本文、根 README、handoff 和 Runtime 台账 HTML 已用真实浏览器检查 `1440×900` / `390×844`，均无页面级横向溢出。

## 真实博查与 AI PM 纵向证据

- 真实中文搜索：官方 Endpoint 认证与中国大陆网络通过；288 ms 返回 10 条，`title/url/site_name/snippet/summary/date_published` 均为 10/10 非空，EvidenceRef 本地重算稳定。
- 真实短超时：1 ms client deadline 在 20 ms 内分类为 `BOCHA_TIMEOUT`，没有回显 Key 或 Provider 错误正文。
- 真实 429 未观察；没有以请求洪泛制造限流。博查标准化响应未观察到 Token/费用字段。
- AI PM 首次真实 Run 暴露“字段 Schema 通过但产物 kind 为通用 `markdown`”问题；该 Run 没有持久化产物或打开 G1。随后增加 MRD 阶段 Schema，强制同时包含 `evidence_index` 与 `mrd`，generic/incomplete 输出会被拒绝。
- 最新隔离 Run `c64d328c-4ae1-4f05-8482-32d16b8f7a84`：首次停在 `waiting_human` PermissionRequest；允许后从 checkpoint 恢复，1 次博查，AI PM 经 1 次有界 schema retry 成功，返回 Evidence Index/MRD 和 10 个 EvidenceRef。
- Reviewer Run `daa10b4d-f657-4215-80a1-64aca91e3efc` 经 1 次有界 schema retry 返回 `pass_with_known_issues`；Red Team Review 已落库并只打开 G1，没有推进到 PRD。
- Journal 和 Event 连续到 sequence 26；失败尝试保留状态但不保存正文，Tool Step 只保存 Evidence 集合哈希和幂等键。
- 脱敏证据：[`d5-bocha-smoke-2026-08-22.json`](./d5-bocha-smoke-2026-08-22.json) / [`d5-ai-pm-research-smoke-2026-08-22.json`](./d5-ai-pm-research-smoke-2026-08-22.json)。

## 当前未完成与 fail-closed 边界

1. 真实产品项目的 G0 仍等待用户决定；隔离 smoke fixture 的 G0/G1 只用于测试，不是产品批准。
2. 真实 G1 用户决定和完整 AG-UI 长连接仍未验证。
3. 真实 429、博查账单/费用对账和来源质量人工评审仍未完成。
4. Key 必须继续只保留在被忽略的本地 `.env` 或进程环境；不得进入聊天、Prompt、Context Pack、测试快照或证据文件。
