# D5 Web / 后端真实投影契约

> 核验日期：2026-08-23  
> 状态：后端接口与 PostgreSQL 数据已在线核验；前端可直接读取。  
> 边界：不代表 PRD/G2、Builder、完整 AG-UI/SSE 或登录强制执行已完成。

## 1. 项目真相源

- 项目名：`销售复盘 Agent`
- `project_id`：`2a3c38e1-9704-4f83-a096-84cb5a5025e7`
- 当前阶段：`prd`
- `context_version`：`3`
- `iteration_version`：`1`
- G1：`approved`，批准后从 Context v2 进入 Context v3 / `prd`
- Builder：未启动；G4 前禁止启动

## 2. 前端读取接口

| 用途 | 接口 | 已提供字段 |
|---|---|---|
| 项目列表 | `GET /api/v1/projects` | id、name、state、context_version、iteration_version、owner、时间 |
| 项目详情 | `GET /api/v1/projects/{project_id}` | 同上 |
| Artifact DAG | `GET /api/v1/projects/{project_id}/graph` | title、kind、status、latest_version、owner_agent、created_at、edges |
| Artifact 全历史 | `GET /api/v1/artifacts/{artifact_id}/versions` | version、context_version、approval_status、created_by、created_at、content_available |
| 指定版本内容 | `GET /api/v1/artifacts/{artifact_id}/content?version={version}` | 受控文本内容与文件元数据 |
| G0/G1 卡 | `GET /api/v1/projects/{project_id}/gates?status=all` | status、Context、目标阶段、关联产物、known_issues[] |
| 用户批准记录 | `GET /api/v1/projects/{project_id}/gate-decisions` | gate_type、decision、decided_by、decided_at、Context 前后版本、target_state |
| 执行/恢复 | `GET /api/v1/projects/{project_id}/execution` | membership、task、run、step、tool_run |
| 事件恢复 | `GET /api/v1/projects/{project_id}/events?cursor={sequence}` | 连续事件；响应头 `X-Event-Cursor` |
| SSE 基础 | `GET /api/v1/projects/{project_id}/events/stream?cursor={sequence}` | SSE 快照重连基础，不等于完整 AG-UI 流式传输 |
| 当前用户/Session | `GET /api/v1/me` | authenticated、user_id、expires_at、reason、auth_enforced |
| 登录 | `POST /api/v1/auth/session` | 邀请码换取 HttpOnly Session；未配置时返回 `AUTH_NOT_CONFIGURED` |
| 退出 | `DELETE /api/v1/auth/session` | 清 Cookie，reason=`logged_out` |

## 3. Artifact 实际数据

| Artifact | artifact_id | 历史版本 | v2 状态 | 创建 Agent |
|---|---|---|---|---|
| Evidence Index | `ed02a37b-ce4b-4a20-b223-3c057ceaf932` | v1、v2 | approved | ai-pm |
| MRD | `6170b1b6-0288-4a33-8358-afd4376f4e6b` | v1、v2 | approved | ai-pm |
| Red Team Review | `e6eeff60-d498-499c-9855-4c45e0bc233e` | v1、v2 | approved | reviewer |

三个 Artifact 的 v1 均保留为 `draft`，v2 为 `approved`；六个版本的内容文件均在线可读。

## 4. G1 真实记录

- `gate_id`：`cec40b01-ba61-494b-a057-b2f5c74173f1`
- 决定：`approve`
- 决定人：`local-admin`
- Context：`2 → 3`
- 目标阶段：`prd`
- 决定时间：`2026-08-22T20:52:47.127610+08:00`
- 已知问题：
  1. `P2`：引用粒度待用户访谈验证。
  2. `P2`：Gong 定价和客户规模缺少直接证据。

Gate 与一次性 PermissionRequest 仍是两套独立记录；Permission 决定不能推进项目阶段。

## 5. 当前仍缺

- Session 接口已实现，但当前运行环境返回 `auth_not_configured`，`auth_enforced=false`；因此不能声称登录已启用或访问控制已完成。
- AG-UI 完整流式传输未完成；当前前端仍使用 `2500ms` cursor 短轮询降级。
- 专用、可回收的开放 Gate/Permission 联合浏览器样本未完成。
- PRD 确定性持久化与 G2 未完成；Builder、MVP、内测和发布均未完成。
- 本轮只提供后端契约；未修改 `apps/web/**`。

## 6. 本轮验证和问题记录

- 主 PostgreSQL 在线执行 `alembic upgrade head`，结果 `20260822_0006 (head)`。
- 新临时数据库完成 `空库 → upgrade head → downgrade 0004 → upgrade head`，最终回到 `0006 (head)` 并删除临时数据库。
- 往返测试先发现两项 migration 问题并已修复：空库不应写入不存在项目的恢复事件；降级不应误删 ToolRun/Permission 审计数据。
- 本线完成时 `pnpm check` 曾通过：Web 13/13、Python 56/56，Ruff/ESLint/TypeScript 通过。随后并行 Runtime 线新增 PRD 路由，当前工作区最新一次 `pnpm check` 因其独立 `agent_router.py` 导入顺序失败；按并线约定本线未覆盖该文件，需 Runtime 线收口后重跑。
- `pnpm test:api:integration`：42/42 通过，保留 1 条 Starlette/httpx 弃用警告。
- 项目事件 sequence 为 `1..66`，共 66 条、无缺号；`cursor=60` 返回 61–66，`X-Event-Cursor=66`。
- 首次直接运行 `pnpm` 因无 TTY 的依赖目录确认失败；CI 模式可执行。并行 Runtime 文件写入期间先后出现未定义名和导入顺序错误；本线仅把新增 `resume` Journal Step 写入测试期望，未覆盖 `agent_router.py` / `agent_runtime.py`。

HTML 阅读版已同步生成，但本轮未做独立桌面/移动浏览器预览，因此不宣称该文档视觉 QA 已通过。
