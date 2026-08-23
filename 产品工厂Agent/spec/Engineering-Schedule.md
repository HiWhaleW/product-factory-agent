# 产品工厂 Agent - 工程排期

> 同步日期：2026-08-23  
> 当前：D10“内部验收”已完成，G5 已由用户批准，进入种子用户内测  
> 项目状态：`seed_beta / Context v10 / iteration v1`

## 1. 当前走到哪里

产品工厂 Agent 的 D1–D10 工程主线和 Beta Candidate 已完成。用户已批准 G5，本机种子内测环境已通过验收，当前开始收集真实内测证据。

| 工程段 | 内容 | 当前状态 |
|---|---|---|
| D1–D2 | 产品范围、Harness、规格冻结 | 已完成 |
| D3–D4 | 工程骨架、数据库、确定性控制面 | 已完成 |
| D5 | 项目对齐、MRD、G0/G1 | 已完成 |
| D6 | PRD、方案、技术栈、G2–G4 | 已完成，G2–G4 已批准 |
| D7 | Builder 后端开发 | 已完成 |
| D8 | Builder 前端开发与 MVP | 已完成 |
| D9 | 独立 QA 与修复 | 已完成 |
| D10 | 内部验收、Beta Candidate、打开 G5 | 已完成；G5 已由用户批准 |
| 平台补齐 | AG-UI/SSE、认证强制执行 | 已完成；浏览器断线恢复与未登录 401 已验证 |
| B1–Bn | 种子用户内测、BRD/G6、发布、反馈 | 已进入种子用户内测；真实用户数据待收集 |

## 2. 当前任务表

| 任务 | 状态 | 真实证据/边界 |
|---|---|---|
| G0–G4 | 已完成 | 均由用户批准，不是 Agent 代批 |
| Builder/Codex | 已完成 | 后端、前端、测试均有 Run/Step/Artifact 证据 |
| MVP | 已完成 | 已进入内部验收 |
| 内部验收 | 已完成材料 | 真实 DeepSeek 样本、测试、浏览器 QA、Known Issues 已保存 |
| Beta Candidate | 已生成 | 只代表可申请进入种子内测，不代表已发布 |
| G5 | 已批准 | `3fb3ef9f-91c9-433f-a56b-10521ec13b4a`；由用户决定 |
| 内测环境验收 | 已完成 | `127.0.0.1:3200/8200`、健康、安全、恢复、回滚均通过 |
| 种子用户内测 | 进行中 | 真实任务、使用和反馈数据待收集 |
| BRD/G6 | 未开始 | 必须使用真实内测数据 |
| 发布/交接 | 未开始 | G6 批准前禁止发布 |
| 数据与反馈 | 未开始 | 发布后进入，并创建下一轮分支 |

## 3. 最新验证

- Web：21/21。
- Python：76/76。
- PostgreSQL 在线集成：46/46。
- production build：通过。
- Alembic：`20260822_0006 (head)`。
- `819×749` 浏览器标注视口：通过，warning/error 为 0。
- 保留 1 条 Starlette/httpx 弃用警告。
- AG-UI/SSE 主通道、断线轮询降级/自动恢复和 HttpOnly Session 强制认证均已通过真实浏览器与 API 验证。

## 4. D1–D10 交付说明

### D1–D2：规格冻结

完成 4 个核心 Agent、12 阶段、G0–G6、Context Pack、Artifact DAG、Execution Task DAG、工具权限和 4 份冻结 Prompt。

### D3–D4：确定性控制面

完成 Next.js/FastAPI monorepo、PostgreSQL、Alembic、Project/Event/Context/Task/Run/Gate/Permission/Artifact 数据模型、幂等、并发和恢复基础。

### D5–D6：产品定义

真实跑通项目对齐、博查调研、MRD、PRD、方案和技术定义；Reviewer 独立审查；G0–G4 逐级由用户批准。

### D7：后端开发

G4 后 Builder 才开始真实 Codex 执行。完成 Runtime → API/数据库 → 测试 → Artifact 证据闭环。

### D8：前端与 MVP

完成真实 Web 投影、群聊、Agent 参与者、Gate/Permission、Artifact DAG、版本预览和 MVP。前端现有内容默认固定，后续确需修改必须提前告知用户。

### D9：独立 QA

Reviewer 检查代码、测试、真模型样本、浏览器和已知问题；问题只重跑受影响的任务和产物，不改写历史。

### D10：内部验收

已生成 QA Report、Known Issues、Beta Candidate、种子用户范围、数据采集 Schema 和退出标准。G5 已由用户批准，内测环境验收通过。

## 5. 后续 B1–Bn

后续不是固定“几天跑完”，而是由真实证据决定：

1. 选择真实种子用户和真实任务。
2. 收集任务成功、使用、失败和反馈数据。
3. 达到退出阈值后生成 BRD / 商业模式确认。
4. 打开 G6，等待用户决定。
5. G6 批准后发布 / 交接。
6. 收集数据与反馈，创建下一轮迭代。

## 6. 人工闸

| Gate | 当前 | 未通过时 |
|---|---|---|
| G0–G4 | 已批准 | 历史决定保留 |
| G5 内部验收 | 已批准 | 允许开展真实种子用户内测 |
| G6 商业与发布 | 未打开 | 不正式发布/交接 |

Gate 与工具 Permission 是两套机制，不能互相代替。

## 7. 完成定义

D10/Beta Candidate 的完成不等于产品发布。正式完成还需要：

- 真实种子用户内测数据。
- 商业 BRD 和 G6 用户批准。
- 正式发布 Deployment Record（内测环境的真实 URL、健康、安全、恢复和回滚记录已完成）。
- 数据与反馈形成下一轮迭代分支。

## 8. 固定工程边界

- 一个跨层任务按 Runtime → API/数据库 → Web → 测试/浏览器 QA → 文档闭环。
- 不拆 Runtime、后端、前端并行线，不等待“并线”。
- 前端非必要不动；确需改动先告知用户。
- 不修改冻结 Prompt。
- 不用 mock、删测试、隐藏错误或降低标准放行。
- Builder 禁止自动 push/deploy/删除工作区。
- AG-UI/SSE 与认证强制执行已完成；短轮询只允许作为断线降级，不得重新作为主通道。
