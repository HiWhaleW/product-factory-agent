# 产品工厂 Agent - 双环境运行说明

> 同步日期：2026-08-24  
> 状态：两套本机环境均已建立；内部可重现基线已更新，用户环境仍保留上一已验收组合包  
> 内部 current / previous：`20260824T074916Z` / `20260824T042123Z`；用户 current / previous：`20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`

## 1. 两套环境是什么

口径边界：销售复盘 Agent 是内部示范项目，其 G6 未打开；产品工厂 Agent 是平台产品；火山引擎 `user-beta` 是真实用户测试平台的云环境。部署该云环境不需先批准销售复盘 Agent G6，也不等于该示范项目正式发布。

| 项目 | 内部验证环境 | 独立用户环境 |
|---|---|---|
| 用途 | 在真实“销售复盘 Agent”上验证完整开发流程 | 给真实种子用户登录并创建自己的项目 |
| Web | `http://127.0.0.1:3200` | `http://127.0.0.1:3300` |
| API | `http://127.0.0.1:8200` | `http://127.0.0.1:8300` |
| 数据 | 保留销售复盘 Agent、内部验收项目与证据 | 独立数据库 `product_factory_user_beta`；初始项目数为 0 |
| 运行目录 | `.runtime/seed-beta/` | `.runtime/user-beta/` |
| Artifact / Workspace | 内部环境专用 | 用户环境专用 |
| Session Secret / 邀请码 | 内部环境专用 | 用户环境专用 |
| 用户 API Key | `.runtime/seed-beta/secrets/`，支持用户配置 OpenAI-compatible 接口；仅管理员可回退到本地测试 Key | `.runtime/user-beta/secrets/`，普通用户必须配置自己的 Key 与接口 |
| 当前角色 | 内部管理员 | 真实种子用户 |

两套环境可以使用同一个内部验收通过的 production 发布包，但绝不能共享数据库、Artifact、Workspace、日志、Session Secret 或邀请码。

### 1.1 “用户环境项目为空”的准确含义

“项目为空”只表示用户数据库不预置任何业务项目及其下游数据，不表示产品页面或 Agent 能力为空。

| 层级 | 用户环境应包含 | 用户环境初始不包含 |
|---|---|---|
| 产品界面 | 首页、首次引导、项目创建/列表、项目工作区、回收箱、设置、个人信息与登录 | 销售复盘 Agent、内部验收项目、测试 fixture |
| Agent 产品能力 | Factory Lead 主入口、AI PM/Builder/Reviewer 协作、12 阶段、G0–G6、Context、Tool、Permission、Artifact DAG、Reviewer 反馈、Run 恢复与 AG-UI/SSE | 内部项目的消息、Artifact、Run、Gate、Permission 和审计数据 |
| 用户数据 | 真实用户、有效邀请、HttpOnly Session；用户创建项目后才产生对应 Context/Run/Artifact | 预置项目、预置产物、预置 Run、预置用户 API Key |
| 模型配置 | OpenAI-compatible HTTPS 接口与用户自有 API Key 的添加、替换、删除能力 | 内部 DeepSeek Key 或任何替用户预填的接口、模型与 Key |

当前真实用户数据库只读核验：项目 `0`、Artifact `0`、Agent Run `0`、用户模型凭据 `0`、内部项目 `0`；用户 `1`、有效邀请码 `1`、Alembic `20260823_0010`。用户创建项目并配置自己的模型 API 后，数据才开始在其独立环境内产生。

## 2. 用户和项目归属

- `users` 是真实用户真相源，`user_invites` 负责邀请码与用户绑定；邀请码只保存哈希。
- HttpOnly Session 绑定数据库用户，项目创建时由后端写入当前用户归属。
- 项目列表只返回当前用户的项目。
- 项目、产物、任务、Run、Gate、Permission 都由后端检查项目归属。
- 跨用户读取返回 404；前端提交其他 owner ID 不会改变归属。
- 用户环境首次登录时项目列表和项目业务数据必须为空；首页、导航、首次引导、项目创建入口、设置和 Agent 产品能力必须完整。不能出现销售复盘 Agent 或内部 fixture。
- 用户 Key 原文不进入 PostgreSQL、页面回包、日志、Context 或 Artifact；数据库只保存 SecretRef、指纹、脱敏尾号以及接口名称/Base URL/模型名。
- Runtime 优先读取当前项目 owner 的 Key；普通用户未配置或受控文件缺失时拒绝执行，不能静默使用内部 DeepSeek Key。

## 3. 正确发布顺序

```text
当前工作区实现
  → 内部环境迁移、测试、production build、健康与浏览器验收
  → 生成并校验可重现内部 current 发布包
  → 用 GitHub Connector 更新 Draft PR
  → 火山引擎账号、地域、网络、资源、费用和拓扑预检
  → 用户确认精确云资源与费用边界
  → 在火山引擎新建独立 user-beta 数据、存储和秘密边界
  → 部署已验收源码基线并完成云上验收
  → 邀请真实种子用户
```

本机独立用户环境的换包是另一条受控放行线：内部验收 → 用户环境 preflight → 绑定同一已验收发布包 → 健康、安全、空项目隔离、恢复与浏览器重验。未经重验不得标记本机 `user_baseline_ready`，但它不是 GitHub 后火山引擎云预检或用户确认后云部署的前置 Gate。不能跳过内部验证直接把工作区代码切到本机用户环境；用户环境也不能反向成为内部开发或销售复盘数据的真相源。

### 3.1 火山引擎目标环境

火山引擎上尚未建立用户测试环境。目标环境必须标识为 `user-beta`，并与两套本机环境分离 PostgreSQL、Artifact、Workspace、日志、用户 Secret Store、Session Secret 和邀请哈希。不复制本地秘密或内部项目。

火山引擎部署前先读 [GitHub 与火山引擎用户测试环境交接](./cloud-user-beta-handoff.html)。带本地 Codex CLI/工作区能力的 Builder 不得直接暴露到公开 veFaaS 函数；必须先对 Web/API、SSE/长任务、数据库、持久化存储与 Builder 做真实拓扑预检。

## 4. 运维命令

### 内部验证环境

```bash
scripts/seed-beta/configure.sh
scripts/seed-beta/release.sh
scripts/seed-beta/start.sh
scripts/seed-beta/health-check.sh
scripts/seed-beta/backup.sh
scripts/seed-beta/restore-check.sh
scripts/seed-beta/rollback.sh
scripts/seed-beta/stop.sh
```

### 独立用户环境

```bash
scripts/user-beta/configure.sh
scripts/user-beta/release.sh
scripts/user-beta/start.sh
scripts/user-beta/health-check.sh
scripts/user-beta/acceptance.sh
scripts/user-beta/backup.sh
scripts/user-beta/restore-check.sh
scripts/user-beta/rollback.sh
scripts/user-beta/stop.sh
```

`scripts/user-beta/release.sh` 默认只绑定内部环境已生成的 `current` 发布包。本次用户明确要求其他内容不动，因此用户环境 current 为受控补丁包 `20260824T042412Z-identity-only`、previous 为 `20260824T032335Z-settings-only`；当前包仅替换已在内部验收的个人信息模块，首页引导、API 设置、项目页、工作区和其他公共资源保持用户基底实现。

## 5. 当前验证

- Web：34/34。
- Python：94/94，另有 48 skipped。
- PostgreSQL：48/48。
- Alembic：`20260823_0010 (head)`。
- ESLint、TypeScript、Ruff、production build：通过。
- 内部 `20260824T074916Z` 的 SHA-256 manifest 在启动核验前后不变；内部启动健康、未登录 401、Session 与 SSE 检查通过。
- 2026-08-24 最新即时核验时 3200/8200/3300/8300 均在监听，两端 `/health`、未登录 401 与 Web 安全响应头通过；进程状态仍须按需实时复核。
- 用户环境历史健康检查通过；当前仍绑定上一已验收组合包，尚未绑定或重新验收 `074916Z`。
- 双用户项目隔离、用户环境首次空项目、内部项目不泄露：通过。
- 项目软删除的 owner 隔离、项目名确认、活跃 Run 阻断、删除后 404 与审计保留：通过。
- 回收箱按 Session owner 隔离；恢复回到原阶段、重复恢复幂等并写入 `project.restored`；不提供永久删除：通过。
- 本次 `/projects` 浏览器 QA：`1440×900`、`390×844` 项目列表/回收箱往返且无水平溢出；5 个项目均有删除按钮；顶栏无“帮助”；warning/error 为 0。
- 用户数据库备份和临时数据库恢复：通过。
- 用户 Web/API 健康、强制认证、HttpOnly Session 和安全响应头：通过；数据库已迁移到 `0010`。
- 用户 Secret Store 临时 Key 添加、响应脱敏、`0600` 权限、删除无残留：通过。
- 用户环境 `095514Z ↔ 155102Z` 双向回滚：通过，最终为 `155102Z`。
- 本次 API 设置页浏览器 QA：添加按钮可触发并对空 Key 给出明确错误；无用户 Key 时不展示虚假删除动作；`390×844` 无水平溢出，warning/error 为 0。用户已确认内部验收通过。
- 内部 `20260823T172749Z` 曾完成四项空态与用户隔离首次引导 QA；其设置页后续纳入 `20260824T021644Z`，并以受控补丁方式进入用户环境。
- 用户环境设置页已同步：四项无配置时全空，删除按钮始终显示且禁用，无内部测试 API 文案；真实添加/删除后数据库凭据和 Secret Store 文件均恢复为 0。
- 两端个人信息已同步精简：只显示名称、账号身份、登录状态和退出登录，不展示用户 ID、运行模式、Session 原因或强制认证诊断；桌面与 `390×844` 浏览器 QA 通过。

## 6. 当前边界

- 两套 URL 都是本机回环地址，不是公网域名。
- GitHub 本轮更新、火山引擎资源预检、公网 HTTPS 和云上 `user-beta` 部署/验收尚未完成。
- G5 已批准，当前可以开展真实种子用户内测；环境就绪不等于真实任务与反馈数据已经达标。
- 内部 current 为 `20260824T074916Z`、previous 为 `20260824T042123Z`；用户环境 current 为 `20260824T042412Z-identity-only`、previous 为 `20260824T032335Z-settings-only`。用户包仍只是在历史设置包上追加个人信息模块，尚未绑定新的可重现内部基线。
- 销售复盘 Agent 若要向其正式发布推进，达到该项目内测退出阈值后才生成 BRD 并打开 G6；G6 只能由用户决定。这不影响平台 `user-beta` 的建立和验收。

详细证据：[独立用户环境验收记录](./evidence/user-environment-acceptance-2026-08-23.html)。
