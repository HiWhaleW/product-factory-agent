# D5 Factory Lead 项目对齐真实冒烟证据

> 日期：2026-08-22  
> 范围：模糊输入 → 澄清 → Project Brief 候选 → G0 打开  
> 结论：真实 DeepSeek 纵向链路到达 `waiting_g0`；项目仍为 `alignment / Context v1`，G0 未批准

## 1. 已验证结果

- 使用 `.env` 中的 `SecretRef` 从后端调用 DeepSeek；证据不包含密钥、Prompt、输入正文或模型输出正文。
- 第 1 轮真实 Factory Lead Run：1 turn、0 retry，产生 3 个版本绑定的澄清问题。
- 第 2 轮真实 Factory Lead Run：1 turn、0 retry，产生结构化 Project Brief；确定性服务创建 Brief v1 并打开 G0。
- 模型没有直接修改项目状态：完成后仍是 `alignment`、`context_version=1`，G0 状态为 `open`。
- Gate 与 PermissionRequest、Artifact DAG 与 Execution Task DAG 仍保持分离。
- 最终证据项目：`2a3c38e1-9704-4f83-a096-84cb5a5025e7`。

## 2. 最终运行元数据

| 项目 | 第 1 轮澄清 | 第 2 轮 Brief/G0 |
|---|---:|---:|
| requested model | `deepseek-chat` | `deepseek-chat` |
| observed model | `deepseek-v4-flash` | `deepseek-v4-flash` |
| turns / retries | 1 / 0 | 1 / 0 |
| Token | 2,774 | 3,859 |
| 延迟 | 3,928.28 ms | 6,199.38 ms |
| 结果 | `clarification_required` | `waiting_g0` |
| checkpoint | `b539247b…b28d93` | `10c30e78…86edd6` |

合计 Token 为 6,633；Provider 未返回费用，`estimated_cost_cny=null`。配置名与服务响应模型名的差异仍未解释。

## 3. 新增确定性契约

- 表：`factory_lead_invocations`，以 `(project_id, idempotency_key)` 唯一约束在模型调用前占位；只保存输入哈希、Context 版本、Run 引用和脱敏结果摘要。
- Context：新项目自动生成 Factory Lead bootstrap Context Pack，主资源精确绑定当前 `ContextVersion`，不伪造预先批准的 Brief。
- Schema：`FactoryLeadOutput` 新增最多 3 条结构化澄清和结构化 `ProjectBriefProposal`。Gate/Transition 若由模型提供仍校验；是否打开 G0 由确定性服务决定。
- API：`POST /api/v1/agent-runtime/projects/{project_id}/factory-lead/alignment-runs`，要求 `Idempotency-Key`、`expected_context_version` 和版本化澄清回答。
- 事件：`factory_lead.invocation.started/completed/failed`、`clarification.answered`，并沿用 `run.*`、`message.created`、`project_brief.*`、`gate.opened`。

## 4. 自动化证据

- Alembic：`20260822_0003` 已在线执行 `upgrade`，并完成 `0003 → 0002 → 0003` 往返。
- `pnpm test:api:integration`：38/38 通过。
- 新增 4 条 PostgreSQL 在线测试：bootstrap Context 精确取回、顺序幂等、并发双击只调用一次、回答澄清后生成 Brief/G0 但不推进状态。
- `pnpm check`：Web Vitest 6/6；Python 35 项通过、38 项在线测试按设计跳过；ESLint、TypeScript、Ruff 通过。
- 保留警告：Starlette `TestClient` 提示未来迁移 `httpx2`。

## 5. 过程失败与修复

1. PostgreSQL 初始状态为无响应的旧进程：`pg_ctl` 判断未运行，但旧主进程和共享内存仍存在。确认只有 5 个 idle 会话后执行 fast shutdown，数据库正常写出 `database system is shut down`；随后在沙箱外正常启动。
2. 第一版第二轮因强制模型同时拼出 Brief、Gate 和 Transition，出现 `DEEPSEEK_SCHEMA_INVALID`，2 次重试后 fail closed。
3. 一次合法 Brief 因顶层 `open_questions` 被错误二次落成未回答澄清，确定性服务返回 `CLARIFICATION_ANSWERS_REQUIRED`。
4. 修复后由控制面根据 Brief 固定创建 G0；最终真实运行 2 轮均 0 retry，未降低字段 Schema，也未自动批准 G0。

## 6. 未完成与下一步

- 本证据只证明 Factory Lead 项目对齐纵向切片，不证明 AI PM、Reviewer、Builder 或完整 D5 效果通过。
- G0 仍需用户真实决定；本次冒烟未代批。
- AI PM 的 `web_research` Adapter 尚不存在，Evidence/MRD/G1 必须继续 fail closed，不能使用模型记忆或 mock 放行。
- 真实 429 未观察；费用映射为空；`deepseek-chat` / `deepseek-v4-flash` 路由差异待供应商确认。
- SSE 当前仍是 snapshot/reconnect foundation；短轮询明确标记为降级。
