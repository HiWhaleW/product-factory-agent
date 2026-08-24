# 产品工厂 Agent - 工程排期

> 同步日期：2026-08-24  
> 平台：产品工厂 Agent D1–D10 已完成，当前为 `internal_reproducible_baseline_ready / cloud_preflight_pending`；本机用户环境为 `local_user_binding_pending`  
> 内部示范项目：销售复盘 Agent 为 `seed_beta / Context v10 / iteration v1`，G5 已批准，G6 未打开

## 1. 当前走到哪里

产品工厂 Agent 的 D1–D10 工程主线和历史本机双环境验收已完成；内部 `20260824T074916Z` 可重现 standalone 基线已建立，独立用户环境尚未绑定或重验新包。销售复盘 Agent 是平台内部示范项目，其 G5 已批准、G6 未打开。火山引擎 `user-beta` 是产品工厂平台的真实用户测试环境，部署它不需先批准销售复盘 Agent G6。

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
| B1–Bn | GitHub 交接、火山引擎云预检与用户测试环境、本机用户环境独立绑定/重验、种子内测、BRD/G6、发布、反馈 | GitHub 与云预检待执行；本机用户绑定是独立放行线；真实用户数据待收集 |

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
| 内部源码/构建可重现基线 | 已完成 | `20260824T074916Z` standalone 包 manifest 启动前后不变；4 份冻结 Prompt 哈希未变 |
| 本机用户环境绑定/重验 | 独立待执行 | current 仍为 `20260824T042412Z-identity-only`；绑定同一 `074916Z` 后必须重验，完成前不得标记本机 `user_baseline_ready`；不阻塞云预检或用户确认后的云部署 |
| GitHub Draft PR 更新 | 待执行 | 只用 Connector；写入前重新核验 head；`force:false`；保持 Draft，不 merge |
| 火山引擎 `user-beta` | 待执行 | 独立数据/存储/秘密；不直接暴露本地 Builder；必须完成 HTTPS、隔离、恢复、回滚和浏览器验收 |
| 平台真实用户测试 | 待云环境就绪 | 收集产品工厂平台的真实任务、使用与反馈；不需销售复盘 Agent G6 |
| 销售复盘 Agent BRD/G6 | 未开始 | 只在准备正式发布该示范项目时，必须使用其真实内测数据 |
| 销售复盘 Agent 发布/交接 | 未开始 | 该项目 G6 批准前禁止宣布正式发布 |
| 数据与反馈 | 未开始 | 发布后进入，并创建下一轮分支 |

## 3. 最新验证

- Web：34/34。
- Python：94/94（48 skipped）。
- PostgreSQL 在线集成：48/48。
- production build、ESLint、TypeScript、Ruff：通过。
- Alembic：`20260823_0010 (head)`。
- `819×749` 浏览器标注视口：通过，warning/error 为 0。
- 保留 1 条 Starlette/httpx 弃用警告。
- AG-UI/SSE 主通道、断线轮询降级/自动恢复和 HttpOnly Session 强制认证均已通过真实浏览器与 API 验证。
- 内部 current / previous 为 `20260824T074916Z` / `20260824T042123Z`；新 current 的 SHA-256 manifest 启动前后不变，4 份冻结 Prompt 哈希未变。用户 current / previous 仍为 `20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`，尚未绑定或重验新包。

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

1. 以已建立的内部 `20260824T074916Z` 可重现构建基线，用 GitHub Connector 更新 Draft PR #1，保持 `force:false`、Draft 且不 merge。
2. 完成火山引擎账号、地域、网络、资源、费用和拓扑只读预检；付费资源或目标不唯一时停止并请用户决定。用户确认后才建立独立 `user-beta`，完成迁移、健康、安全、隔离、Secret Store、恢复/回滚和浏览器 QA。
3. 本机独立用户环境如需换包，另行做 preflight、绑定同一基线并重新完成健康、安全、隔离及桌面/移动浏览器验收；这不是第 2 步的前置 Gate。
4. 选择真实用户和真实任务，收集产品工厂平台的任务成功、使用、失败和反馈数据。
5. 销售复盘 Agent 保持种子内测；若准备正式发布该示范项目，再以其真实证据生成 BRD、打开 G6 并等待用户决定。

火山引擎 `user-beta` 是产品工厂平台的用户测试基础设施，不需销售复盘 Agent G6，也不是该示范项目正式发布。

## 6. 人工闸

| Gate | 当前 | 未通过时 |
|---|---|---|
| G0–G4 | 已批准 | 历史决定保留 |
| G5 内部验收 | 已批准 | 允许开展真实种子用户内测 |
| 销售复盘 Agent G6 商业与发布 | 未打开 | 不宣布该示范项目正式发布/交接；不阻塞平台 `user-beta` |

Gate 与工具 Permission 是两套机制，不能互相代替。

## 7. 完成定义

D10/Beta Candidate 的完成不等于销售复盘 Agent 正式发布。该示范项目正式完成还需要：

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
