# 产品工厂 Agent - 当前交接

> 日期：2026-08-24  
> 平台：产品工厂 Agent，下一步为 GitHub 更新 → 火山引擎 `user-beta`  
> 内部示范项目：销售复盘 Agent，第 9/12 阶段，`seed_beta / Context v10 / iteration v1`  
> 示范项目闸口：G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a` 已批准；G6 尚未打开

## 一句话结论

产品工厂 Agent 是平台产品，下一步可直接更新 GitHub 并部署火山引擎 `user-beta`，无需先批准销售复盘 Agent G6。销售复盘 Agent 只是内部示范项目，当前停在种子内测，其 G6 未打开。火山引擎 `user-beta` 是供真实用户测试平台的环境，不等于销售复盘 Agent 正式发布。

内部环境 current 已更新为可重现 standalone 发布包 `20260824T074916Z`，previous 为 `20260824T042123Z`；用户环境仍为 `20260824T042412Z-identity-only`，previous 为 `20260824T032335Z-settings-only`。`074916Z` 的 SHA-256 manifest 在启动核验前后保持一致；用户环境尚未绑定或重新验收该包，既有用户验收结论不得自动扩展到新基线。2026-08-24 最新即时核验时四个本机端口均在监听，两端健康、未登录 401、Session 与安全响应头通过；进程状态可能随运维动作变化，后续仍须实时核验。既有桌面/移动浏览器与用户空项目隔离验收继续作为历史证据保留。

产品定位必须保持为 **AI Native**：Agent 是主要执行者，群聊是主交互入口，Context、工具调用、产物、Reviewer、Gate 和反馈循环是产品本身，不是普通后台系统上的附加 AI 功能。

## 已完成

- G0 项目对齐、G1 MRD、G2 PRD、G3 方案和 G4 技术栈均已由用户批准。
- DeepSeek、博查、有界 LangGraph、Run/Step/checkpoint 和确定性 Gate/Permission 控制面已真实运行。
- Builder 已通过 Codex CLI 真实执行，不再是“只写方案”。
- 后端开发 → 前端开发 → MVP → 内部验收已按顺序完成。
- Beta Candidate、内部 QA 和 Known Issues 已写入同源 PostgreSQL/Artifact。
- Web 已接真实项目、事件、Agent、Gate、Artifact DAG 和版本历史。
- 主 Agent 邀请子 Agent 入群的互动和子 Agent 自我介绍已恢复。
- 143 条执行记录拆成 38 个消息间处理组，显示顺序为“用户消息 → 处理过程 → Agent 回复”。
- 工具过程已改成通俗中文，处理步骤文字遮挡已解决。
- 平台 AG-UI/SSE 主通道与认证强制执行已补齐；短轮询仅在 SSE 断线时降级。
- G5 已由用户批准；内部验证入口 `http://127.0.0.1:3200` 保留销售复盘 Agent，独立用户入口 `http://127.0.0.1:3300` 首次登录为空项目。
- “为空项目”只指用户数据库不预置项目及其 Artifact/Run/Gate 等业务数据；用户版本仍包含完整首页、引导、项目创建、Agent 工作区、12 阶段、控制面与设置能力。
- 数据库已引入真实 `users`、邀请码和项目所有者；项目、产物、任务、Run、Gate、Permission 均按当前 Session 用户隔离。
- `/` 已成为独立首页，`/projects` 是真实项目列表页；顶部导航为“首页 / 项目列表 / 设置”，顶部“个人信息”承载原用户与会话内容。
- “真实项目”已增加受控软删除：项目名二次确认、Session owner 校验、活跃 Run 阻断、删除事件审计；顶栏无效“帮助”、`?` 快捷键和虚假快捷键说明已移除。
- `/projects` 已增加用户隔离回收箱；可恢复到删除前阶段，重复恢复幂等，恢复写入 `project.restored`，不提供永久删除。
- 邀请码登录成功后统一 `replace` 到 `/` 首页；两端“个人信息”只显示名称、账号身份、登录状态和退出登录，不展示内部诊断字段。
- `/projects` 的“去处理”和“继续项目”已统一尺寸并居中：桌面 `88×44px`，移动 `157.5×44px`。
- 设置页只保留 API 配置：用户可添加、替换和删除专属 Key，并配置 OpenAI-compatible HTTPS Base URL 与模型名；普通用户无配置时四项表单全部为空。首次引导按真实用户独立记录，只有用户明确跳过或完成后才标记已看。
- Key 原文只存于用户隔离、权限为 `0600` 的受控文件；数据库和 API 只保存/返回脱敏元数据与非敏感接口配置。Runtime 优先使用项目 owner 的配置，普通用户未配置时 fail closed；本地环境变量 Key 只允许内部管理员测试回退。

## 最新验证

| 验证 | 结果 |
|---|---|
| Web | 34/34 |
| Python | 94/94（48 skipped） |
| PostgreSQL 集成 | 48/48 |
| Build / 静态检查 | production build、ESLint、TypeScript、Ruff 通过 |
| Alembic | `20260823_0010 (head)` |
| 发布完整性 | `20260824T074916Z` manifest 在启动前后不变，standalone 包可反向校验 |
| 浏览器 | 既有内部与用户包的桌面/移动验收通过；`074916Z` 尚未绑定用户环境或获得新一轮用户验收 |

保留 1 条 Starlette/httpx 弃用警告。AG-UI/SSE 是主通道；`2500ms` cursor 轮询只在断线时降级，恢复后自动停止。生产环境必须配置并开启 HttpOnly Session 认证，否则 API 拒绝启动。

## 当前不能做

- 用户环境已可用于受控种子内测；只能收集真实任务、成功、失败、使用和反馈数据，不得伪造。
- 没有真实内测数据前不得生成“已确认”的商业结论。
- 销售复盘 Agent G6 未批准前，不得宣布该示范项目正式发布；这不阻塞平台 `user-beta` 部署。
- 前端非必要不动；确需修改必须提前告诉用户。
- 不修改冻结的 4 份 Agent Prompt。
- 不使用 mock、删测试或隐藏错误放行。

## 后续流程

1. 以内部 `20260824T074916Z` 作为可重现源码/构建基线候选，用 GitHub Connector 更新 Draft PR #1；写入前重新核验远端 head，保持 Draft、`force:false` 且不 merge。
2. 将独立用户环境部署到火山引擎，明确标识为 `user-beta`；完成 HTTPS、认证、SSE、空项目隔离、Secret Store、备份/恢复、回滚和真实浏览器验收。
3. 使用真实用户和真实任务测试产品工厂平台，收集平台成功、失败、使用和反馈数据。
4. 销售复盘 Agent 保持种子内测；若后续要正式发布该示范项目，再以其真实内测证据生成 BRD、打开 G6 并等待用户决定。

火山引擎上的 `user-beta` 是产品工厂平台的受控用户测试基础设施，可在销售复盘 Agent G6 之前建立；它不是该示范项目的正式发布。详细执行和停止条件见 [GitHub 与火山引擎用户测试环境交接](./cloud-user-beta-handoff.html)。

## 项目和两套环境

- 真实项目 ID：`2a3c38e1-9704-4f83-a096-84cb5a5025e7`。

| 项目 | 内部验证环境 | 独立用户环境 |
|---|---|---|
| 用途 | 验证销售复盘 Agent 的开发全流程 | 供真实种子用户创建自己的项目 |
| Web / API | `127.0.0.1:3200` / `127.0.0.1:8200` | `127.0.0.1:3300` / `127.0.0.1:8300` |
| 数据 | 保留销售复盘 Agent 与内部验收数据 | 独立数据库；首次登录项目为空 |
| 运行目录 | `.runtime/seed-beta/` | `.runtime/user-beta/` |
| 健康检查 | `scripts/seed-beta/health-check.sh` | `scripts/user-beta/health-check.sh` |

内部环境 current 为 `20260824T074916Z`、previous 为 `20260824T042123Z`；用户环境 current 为 `20260824T042412Z-identity-only`、previous 为 `20260824T032335Z-settings-only`，用户数据库为 `20260823_0010`。新内部包尚未绑定用户环境。两套环境的数据库、Artifact、Workspace、用户 Secret Store、日志、Session Secret 和邀请码互相独立。详细说明见 [双环境运行说明](./environments.html)。

最新真实核验：用户 Web/API 健康检查通过，首次登录项目为空且内部项目数为 0；Secret Store 临时 Key 添加、响应脱敏、`0600` 权限、删除无残留通过；迁移后备份恢复到隔离临时库通过；`095514Z ↔ 155102Z` 双向回滚通过并最终恢复到新包。

- 可回收测试 fixture：`c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001`，不得冒充真实业务项目。
- GitHub：`HiWhaleW/product-factory-agent`，`codex/initial-import`，Draft PR #1；2026-08-24 只读核验 PR head 为 `69eb31d22430522f32c8db6b1151336756f42d01`。任何远端写入前用 Connector 重新核验 head，禁止 `gh`、本地 push 和 force push。

## 仍未完成

- GitHub 本轮更新和火山引擎 `user-beta` 部署/验收。
- 将可重现内部基线 `20260824T074916Z` 绑定到独立用户环境并完成健康、隔离及桌面/移动重新验收；完成前不得标记 `user_baseline_ready`。
- 真实种子用户任务、使用和反馈数据。
- 首页引导 v2 已进入内部 `20260824T074916Z`；用户环境仍保留历史组合包，尚未获得这次可重现基线的绑定与验收。
- Factory Lead 尚无确定性 feasibility/preflight 分类器；当前只能依赖模型澄清和 Run 预算上限，不能保证在第一次模型调用前识别所有绝对不可能目标。
- BRD/G6、正式发布/交接、数据与反馈。
- 当前用户入口仍是本机 URL；公网域名、HTTPS 和外部可访问部署尚未完成。
- 用户环境 current 为 `20260824T042412Z-identity-only`、previous 为 `20260824T032335Z-settings-only`；当前个人信息补丁可回退到上一已验收设置包。
- 真实 429、博查费用/账单、来源质量人工评审和模型路由差异确认。

## 入口

- [Design QA](../design-qa.html)
- [工程排期](../产品工厂Agent/spec/Engineering-Schedule.html)
- [产品生命周期](./product-lifecycle.html)
- [交接提示词](./HANDOFF_PROMPT.md)
- [运维手册](./operator-runbook.md)
- [种子内测环境验收记录](./evidence/seed-beta-environment-acceptance-2026-08-23.html)
- [独立用户环境验收记录](./evidence/user-environment-acceptance-2026-08-23.html)
- [双环境运行说明](./environments.html)
- [GitHub 与火山引擎用户测试环境交接](./cloud-user-beta-handoff.html)
