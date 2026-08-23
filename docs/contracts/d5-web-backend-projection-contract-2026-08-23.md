# D5 Web / 后端真实投影契约

> 核验日期：2026-08-23  
> 状态：后端接口与 PostgreSQL 数据已在线核验；前端可直接读取。  
> 边界：销售复盘项目已真实完成 PRD/Review v1 并打开 G2，但 G2 尚未由用户决定；Builder、完整 AG-UI/SSE 和登录强制执行仍未完成。

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

同一 Gate 接口现在也可读取真实 G2 `fdac9cd1-3cb8-4a98-b87d-18d8ef779e82`，状态为 `open`；该记录只能由用户决定。

## 3. Artifact 实际数据

| Artifact | artifact_id | 历史版本 | v2 状态 | 创建 Agent |
|---|---|---|---|---|
| Evidence Index | `ed02a37b-ce4b-4a20-b223-3c057ceaf932` | v1、v2 | approved | ai-pm |
| MRD | `6170b1b6-0288-4a33-8358-afd4376f4e6b` | v1、v2 | approved | ai-pm |
| Red Team Review | `e6eeff60-d498-499c-9855-4c45e0bc233e` | v1、v2 | approved | reviewer |
| PRD | `71d3b81a-1d48-4501-9eb7-20209af85d1b` | v1 | waiting_gate | ai-pm |
| PRD Review | `44c79e5a-d76c-4b1c-b9f3-b795142e2dc1` | v1 | waiting_gate / pass | reviewer |

Evidence Index、MRD 和 Red Team Review 的 v1 均保留为 `draft`，v2 为 `approved`；PRD/Review v1 等待 G2。历史版本和当前内容均由同源接口读取。

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
- 专用、可回收的开放 Gate/Permission fixture `c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001` 数据已存在，桌面/移动联合浏览器验收仍未完成。
- 真实项目 PRD/Review v1 与 G2 open 已完成；G2 用户决定、方案/G3 和技术栈/G4 尚未完成。
- 当前统一工作区已包含 Web 真实投影；后续不再等待 Runtime、后端或前端独立并线。

## 6. 本轮验证和问题记录

- 主 PostgreSQL 在线执行 `alembic upgrade head`，结果 `20260822_0006 (head)`。
- 新临时数据库完成 `空库 → upgrade head → downgrade 0004 → upgrade head`，最终回到 `0006 (head)` 并删除临时数据库。
- 往返测试先发现两项 migration 问题并已修复：空库不应写入不存在项目的恢复事件；降级不应误删 ToolRun/Permission 审计数据。
- 2026-08-23 当前统一工作区 `pnpm check`：Web 13/13、Python 60/60，Ruff/ESLint/TypeScript 全部通过。
- `pnpm test:api:integration`：44/44 通过，保留 1 条 Starlette/httpx 弃用警告。
- PRD 流程新增事件 sequence `67–82`，包含 Run、Tool、Artifact、Context、PRD、Review 和 Gate open，可按 cursor 恢复。
- 首次直接运行 `pnpm` 因无 TTY 的依赖目录确认失败；使用 `CI=true` 后当前统一工作区全量检查通过。历史并行写入问题已收口，不再作为当前阻塞。

HTML 阅读版已同步，并于 2026-08-23 用 ego-browser 在 `1440×900` 与 `390×844` 复验：最新 G2 口径、统一工作区边界与 G4/Builder 阻断均可读，页面无横向溢出。
