# D5 PRD Runtime 真实执行记录

> 日期：2026-08-23  
> 结论：销售复盘 Agent 的真实 AI PM PRD Run、Reviewer clean-review、确定性 Artifact 持久化和 G2 open 已完成。G2 未决定，项目仍为 `prd / Context v3`，Builder 未启动。

## 真实纵向结果

| 对象 | 结果 |
|---|---|
| 项目 | `2a3c38e1-9704-4f83-a096-84cb5a5025e7`，`prd / Context v3 / iteration v1` |
| PRD Context Pack | `7e918f18-8699-406f-86ca-7d90e6edc6a9` |
| AI PM Run | `9c7ffc14-afe2-4abb-b7f7-0c9929d2d327`，成功，1 turn / 0 retry，9,399 Token |
| PRD | `71d3b81a-1d48-4501-9eb7-20209af85d1b` v1，`waiting_gate` |
| Reviewer Run | `6442a2fa-9975-4545-ae8e-21c0a1f5ae7b`，成功，1 turn / 0 retry / 0 tools，10,552 Token |
| PRD Review | `44c79e5a-d76c-4b1c-b9f3-b795142e2dc1` v1，verdict `pass`，`waiting_gate` |
| G2 | `fdac9cd1-3cb8-4a98-b87d-18d8ef779e82`，`open`，未决定 |

两个真实 Run 均请求 `deepseek-chat`，服务端返回元数据为 `deepseek-v4-flash`；模型路由差异仍待确认。Provider 返回 Token，不返回费用，系统没有伪造费用。

## Run、Step、Tool 与 cursor

- AI PM：`runtime_start → model → checkpoint → artifact_store`。
- Reviewer：`runtime_start → model → checkpoint → artifact_store`。Reviewer 模型本身未调用工具；最后的 `artifact_store` 是确定性服务保存审查产物。
- 两次 `artifact_store` 均先由 Tool Policy 判定为 `allow`，再以 Run 绑定的幂等键保存；RunStep 和 ToolRun 均标记外部副作用已确认。
- PRD 流程事件为 sequence `67–82`，含 `run.started/completed`、`tool_run.started/completed`、`artifact.created`、`context.pack_created`、`prd.submitted`、`gate.opened` 和 `prd.reviewed`，可由 cursor 恢复。
- Runtime 没有直接推进 Project 状态，也没有批准 G2。

## fail-closed 记录

首次真实 AI PM 模型 Run `8b42fae4-affc-40e1-bf7f-0102f0b57387` 成功，但输出遗漏契约要求的 `status=waiting_review`，确定性提交接口拒绝写入：没有创建 PRD、没有打开 G2。修正严格 Schema 后重新真实运行，才生成本页记录的 PRD 与 G2。

这说明“模型调用成功”不等于“业务提交成功”；Schema 不合规时不会用 mock 或宽松解析继续。

## Context Pack 边界

- AI PM 只读取已批准的 PRD Context Pack：MRD v2、Evidence Index v2、Red Team Review v2 及精确版本元数据。
- Reviewer 只读取 `prd-review/v1` Pack 中精确绑定的 PRD candidate；它被标明为 draft/waiting review，不冒充批准材料。
- 不共享隐藏思维链、整段群聊、无关草稿、Secret 原值、搜索全文或其他项目数据。
- 脱敏证据不保存 Prompt 和模型输出正文。

## 前端联合验收 fixture

- 项目：`c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001`（`D5 Gate/Permission 联合验收（可回收）`）。
- 开放 G2：`ff88c878-171c-4d33-90e1-221c58d64df6`。
- 开放 PermissionRequest：`b765256c-2d3b-4130-9adb-9e1ea5cee28d`。
- 当前可恢复 Run：`e8f84246-fc58-4051-801c-13abc7b5d00c`。
- 历史恢复 Run：`1c8afa41-aed0-4620-abb6-41f84a76b3d8`，包含 `run.waiting → permission.decided → run.resumed` 及 Tool 完成事件。
- 验收操作后可执行 `PYTHONPATH=apps/api UV_CACHE_DIR=.uv-cache uv run python -m app.agents.acceptance_fixture --reseed` 恢复初始状态。Fixture 明确标记为测试项目，不得当作真实业务产物。

## 验证与未完成项

- `pnpm check`：本轮代码完成后已通过，Web 13 项、Python 60 项，Ruff、TypeScript、ESLint 均通过。
- PostgreSQL 完整集成测试：44/44 通过；Alembic 为 `20260822_0006 (head)`。
- README、handoff 和本 PRD 证据 HTML 已用 ego-browser 检查 `1440×900` / `390×844`，标题与链接存在，页面级横向溢出均为 0。
- 第一次全量集成测试因沙箱禁止访问 `127.0.0.1:5432` 失败；获得本机访问权限后原命令 44/44 通过，未隐藏该环境失败。
- 保留一条 Starlette TestClient/httpx 弃用警告。
- 真实 G2 仍需用户决定；G4 前禁止 Builder。
- `2500ms` cursor 轮询仍是降级方案；AG-UI/SSE 未完成。
- 不宣称 Builder、MVP、内测或发布完成。

机器可读证据：[d5-prd-runtime-flow-2026-08-23.json](./d5-prd-runtime-flow-2026-08-23.json)。
