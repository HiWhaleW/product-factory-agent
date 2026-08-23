# 产品工厂 Agent

> 当前阶段：第 9/12 阶段“种子用户内测”  
> 项目状态：`seed_beta / Context v10 / iteration v1`  
> 当前闸口：G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a` 已由用户批准；G6 尚未打开  
> 最后同步：2026-08-23

产品工厂 Agent 是一个 **AI Native 产品**：AI Agent 不是附加聊天框，而是产品的主要执行者。用户用自然语言提出目标，Agent 理解上下文、调用工具、生成产物、接受 Reviewer 审查并持续推进；确定性控制面负责 Gate、权限、预算、幂等和审计。左侧是用户与主/子 Agent 的群聊，右侧是可追溯的产物画布。

## 当前进度

| 项目 | 状态 |
|---|---|
| G0–G4 | 已由用户批准 |
| 方案和技术栈 | 已完成并通过 Reviewer |
| Builder | 已真实执行 Codex，实现后端、前端和测试 |
| 后端开发 → 前端开发 → MVP | 已完成 |
| 内部验收 | 已完成验收材料，Beta Candidate 已生成 |
| G5 | 已由用户批准 |
| 内部验证环境 | 已补齐真实用户、项目归属和跨用户隔离 |
| 用户自有 API | 设置页可添加、替换和删除专属 API Key，并配置 OpenAI-compatible 接口和模型名；普通用户未配置时 Agent 拒绝执行 |
| 页面结构 | `/` 首页、`/projects` 真实项目页、`/settings` API 设置；真实项目支持受控软删除、用户隔离回收箱与恢复，顶部已移除无效“帮助”入口 |
| 独立用户环境 | 已同步已验收包 `20260823T155102Z`；独立数据库已迁移到 `0010`，Secret Store、恢复和跨版本回滚通过 |
| 真实种子用户数据、BRD/G6、发布 | 尚未完成 |

当前允许开始真实种子用户内测，但不得伪造任务或反馈数据；G6 前不得正式发布。

## 最新验证

- Web：26/26。
- Python：86/86。
- PostgreSQL 集成：48/48。
- Next.js production build：通过。
- Alembic：`20260823_0010 (head)`。
- 保留 1 条 Starlette/httpx 弃用警告。
- 真实 DeepSeek 模型验收、Builder/Codex 执行和真实浏览器 QA 均有记录。
- AG-UI/SSE 已成为事件主通道，支持持久化 cursor、`Last-Event-ID`、心跳、断线轮询降级和自动重连。
- 认证强制执行已完成：生产环境未开启认证会拒绝启动，受保护 API 使用 HttpOnly Session 且未登录返回 401。
- 用户 API Key 原文只写入权限为 `0600` 的用户隔离 Secret Store；PostgreSQL 只保存 SecretRef、指纹、脱敏尾号与非敏感接口元数据，验证错误也会脱敏。Runtime 使用用户选择的 OpenAI-compatible HTTPS Base URL 与模型名；内部环境变量 Key 仅允许管理员测试回退。
- 内部验证环境为 `http://127.0.0.1:3200` / `http://127.0.0.1:8200`，保留销售复盘 Agent 和内部验收数据。
- 独立用户环境为 `http://127.0.0.1:3300` / `http://127.0.0.1:8300`，使用独立数据库，首次登录项目列表为空，内部项目未泄露；当前发布包为 `20260823T155102Z`，Alembic 为 `20260823_0010`。
- 用户已确认内部浏览器验收通过。用户环境的 API Key 添加、响应脱敏、`0600` 权限、删除无残留、迁移后备份恢复，以及 `095514Z ↔ 155102Z` 双向回滚均通过；最终恢复到新包。

## 最新群聊体验

- 主 Agent 邀请子 Agent 入群，并由子 Agent 真实自我介绍。
- 每次对话按“用户消息 → 处理过程 → Agent 回复”显示。
- 143 条执行记录已拆成 38 个消息间处理组，不再堆在阶段末尾。
- 技术事件已改为通俗中文，例如“准备资料”“调用网络搜索工具：博查”“调用代码实现工具：Codex”。
- 处理步骤使用“时间 + 标题 + 说明”，已解决文字遮挡。
- 用户标注的 `819×749` 视口浏览器检查通过，控制台 warning/error 为 0。

## 后面还有什么

1. 在独立用户环境使用真实种子用户和真实任务开展内测，收集成功、失败、使用和反馈数据。
2. 验证 Reviewer 已知问题、真实 429、博查费用/账单、来源质量和第三方兼容模型效果，不得伪造数据。
3. 达到退出阈值后生成 BRD / 商业模式确认并打开 G6。
4. 用户决定 G6；批准后才发布 / 交接，并在发布后进入下一轮迭代。

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
