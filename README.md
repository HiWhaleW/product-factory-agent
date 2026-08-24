# 产品工厂 Agent

> 平台产品：“产品工厂 Agent”，当前为 `internal_reproducible_baseline_ready / cloud_preflight_pending`  
> 内部示范项目：“销售复盘 Agent”，`seed_beta / Context v10 / iteration v1`，第 9/12 阶段  
> 示范项目闸口：G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a` 已批准；G6 尚未打开  
> 最后同步：2026-08-24

产品工厂 Agent 是一个 **AI Native 产品**：AI Agent 不是附加聊天框，而是产品的主要执行者。用户用自然语言提出目标，Agent 理解上下文、调用工具、生成产物、接受 Reviewer 审查并持续推进；确定性控制面负责 Gate、权限、预算、幂等和审计。左侧是用户与主/子 Agent 的群聊，右侧是可追溯的产物画布。

## 当前进度

三个对象不能混用：销售复盘 Agent 是内部示范项目；产品工厂 Agent 是平台本身；火山引擎 `user-beta` 是供真实用户测试平台的独立环境。部署 `user-beta` 不需要先批准销售复盘 Agent 的 G6，也不等于销售复盘 Agent 正式发布。

| 项目 | 状态 |
|---|---|
| 销售复盘 Agent G0–G4 | 已由用户批准 |
| 方案和技术栈 | 已完成并通过 Reviewer |
| Builder | 已真实执行 Codex，实现后端、前端和测试 |
| 后端开发 → 前端开发 → MVP | 已完成 |
| 内部验收 | 已完成验收材料，Beta Candidate 已生成 |
| 销售复盘 Agent G5 | 已由用户批准 |
| 内部验证环境 | current / previous 为 `20260824T074916Z` / `20260824T042123Z`；可重现 standalone 基线已建立 |
| 用户自有 API | 设置页可添加、替换和删除专属 API Key，并配置 OpenAI-compatible 接口和模型名；普通用户未配置时 Agent 拒绝执行 |
| 页面结构 | `/` 首页、`/projects` 真实项目页、`/settings` API 设置；真实项目支持受控软删除、用户隔离回收箱与恢复，顶部已移除无效“帮助”入口 |
| 独立用户环境 | 当前为 `20260824T042412Z-identity-only`：以已验收设置包为基底，只追加精简个人信息 |
| 交接下一步 | 用 GitHub Connector 更新 Draft PR → 火山引擎账号/拓扑/费用预检 → 用户确认后建立受控 `user-beta` |
| 销售复盘 Agent 的真实内测数据、BRD/G6、正式发布 | 尚未完成；不阻塞平台 `user-beta` 部署 |

当前可直接准备和部署平台 `user-beta`，无需等待销售复盘 Agent G6。云上环境就绪后只能称为平台用户测试环境，不得伪造真实用户任务或反馈数据。

## 最新验证

- Web：34/34。
- Python：94/94（48 skipped）。
- PostgreSQL 集成：48/48。
- Next.js production build、ESLint、TypeScript、Ruff：通过。
- Alembic：`20260823_0010 (head)`。
- 保留 1 条 Starlette/httpx 弃用警告。
- 真实 DeepSeek 模型验收、Builder/Codex 执行和真实浏览器 QA 均有记录。
- AG-UI/SSE 已成为事件主通道，支持持久化 cursor、`Last-Event-ID`、心跳、断线轮询降级和自动重连。
- 认证强制执行已完成：生产环境未开启认证会拒绝启动，受保护 API 使用 HttpOnly Session 且未登录返回 401。
- 用户 API Key 原文只写入权限为 `0600` 的用户隔离 Secret Store；PostgreSQL 只保存 SecretRef、指纹、脱敏尾号与非敏感接口元数据，验证错误也会脱敏。Runtime 使用用户选择的 OpenAI-compatible HTTPS Base URL 与模型名；内部环境变量 Key 仅允许管理员测试回退。
- 内部验证环境为 `http://127.0.0.1:3200` / `http://127.0.0.1:8200`，保留销售复盘 Agent 和内部验收数据；current / previous 为 `20260824T074916Z` / `20260824T042123Z`。新 current 的 SHA-256 manifest 在启动前后不变，4 份冻结 Prompt 哈希未变。
- 独立用户环境为 `http://127.0.0.1:3300` / `http://127.0.0.1:8300`，使用独立数据库，首次登录项目列表为空，内部项目未泄露；current / previous 仍为 `20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`，Alembic 为 `20260823_0010`。它尚未绑定或重新验收 `074916Z`。
- “项目列表为空”只表示不预置项目、Artifact、Run 或用户 API 配置；首页、引导、项目创建、双栏 Agent 工作区、12 阶段、Gate、Tool、Artifact、Reviewer、恢复和设置能力完整存在。
- 用户已确认内部浏览器验收通过。用户环境的 API Key 添加、响应脱敏、`0600` 权限、删除无残留、迁移后备份恢复，以及 `095514Z ↔ 155102Z` 双向回滚均通过；最终恢复到新包。
- 设置页仍保持四项空态、禁用删除按钮和无内部文案。两端“个人信息”现只显示名称、账号身份、登录状态和退出登录；用户 ID、运行模式、Session 原因和强制认证诊断已移除。首页引导仍保持原用户包实现。

当前平台状态为 `internal_reproducible_baseline_ready / cloud_preflight_pending`。既有本机用户环境验收不得自动扩展到新内部包，也不得标记 `user_baseline_ready`；这条本机放行边界不阻塞 GitHub 后的云预检。

## 最新群聊体验

- 主 Agent 邀请子 Agent 入群，并由子 Agent 真实自我介绍。
- 每次对话按“用户消息 → 处理过程 → Agent 回复”显示。
- 143 条执行记录已拆成 38 个消息间处理组，不再堆在阶段末尾。
- 技术事件已改为通俗中文，例如“准备资料”“调用网络搜索工具：博查”“调用代码实现工具：Codex”。
- 处理步骤使用“时间 + 标题 + 说明”，已解决文字遮挡。
- 用户标注的 `819×749` 视口浏览器检查通过，控制台 warning/error 为 0。

## 后面还有什么

1. 以已建立的内部 `20260824T074916Z` 可重现源码/构建基线，用 GitHub Connector 安全更新 Draft PR #1；写入前重新核验 head，保持 `force:false`、Draft 且不 merge。
2. 按 `docs/cloud-user-beta-handoff.md` 核验火山引擎账号、地域、网络、资源、费用和拓扑；付费资源或目标不唯一时先请用户决定。
3. 用户确认精确资源边界后，将同一可重现基线部署到火山引擎，只作为 `user-beta` 种子用户测试环境；完成 HTTPS、认证、SSE、空项目隔离、Secret Store、备份/恢复、回滚和浏览器验收。本机用户环境仍保留旧包，后续绑定需单独验收但不阻塞云预检。
4. 用真实用户和真实任务测试产品工厂平台，收集平台的任务成功、失败、使用和反馈数据，不得伪造。
5. 销售复盘 Agent 保持在种子内测。若后续要正式发布该示范项目，再以其真实内测证据生成 BRD、打开 G6 并等待用户决定。

## 入口

1. [当前交接](./docs/handoff.html)
2. [工程排期](./产品工厂Agent/spec/Engineering-Schedule.html)
3. [设计与浏览器 QA](./design-qa.html)
4. [产品生命周期](./docs/product-lifecycle.html)
5. [权威交互视觉基线](./产品工厂Agent_Harness表.html)
6. [规格索引](./产品工厂Agent/spec/index.html)
7. [种子内测环境验收记录](./docs/evidence/seed-beta-environment-acceptance-2026-08-23.html)
8. [独立用户环境验收记录](./docs/evidence/user-environment-acceptance-2026-08-23.html)
9. [双环境运行说明](./docs/environments.html)
10. [GitHub 与火山引擎用户测试环境交接](./docs/cloud-user-beta-handoff.html)

## 固定边界

- 不能把它做成“传统 CRUD 系统 + AI 聊天框”；Agent、Context、Tool、Artifact、Gate、Reviewer 和反馈循环必须是一等产品能力。
- 前端现有内容默认固定；如确需修改，必须提前告知用户。
- 不修改冻结的 4 份 Agent Prompt。
- 不使用 mock、删测试或隐藏错误放行。
- Gate 只能由用户决定，Agent 不得代批。
- 后续跨层任务仍按 Runtime → API/数据库 → Web → 测试/浏览器 QA → 文档完整闭环。
- `2500ms` cursor 短轮询只在 SSE 断线时临时启动，SSE 恢复后自动停止。
- GitHub 远端操作只能使用 Connector；写入前重新核验 head，禁止 `force push` 和 `gh`。

## 文档权威顺序

1. 用户最新确认。
2. `产品工厂Agent/spec/` 权威规格。
3. `docs/` 当前交接、架构和运维摘要。
4. 根目录原始工程手册。

规格中尚无代码、migration 或真实运行证据覆盖的内容仍是未来契约，不是已完成功能。
