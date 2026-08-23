# 产品工厂 Agent - 正式交接提示词

> 当前状态：`seed_beta / Context v10 / iteration v1`  
> 当前闸口：G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a` 已批准；G6 尚未打开  
> 内部发布包：`20260823T155102Z`；用户环境发布包：`20260823T155102Z`

## 可直接复制

```text
你现在接手“产品工厂 Agent”后续开发。

项目根目录：
<PROJECT_ROOT>

第一原则：这是一个 AI Native 产品。

- Agent 是主要执行者，不是传统后台里的附加聊天框。
- 用户通过自然语言表达目标；Agent 必须读取 Context、规划任务、调用受控工具、生成 Artifact、接受 Reviewer 审查，并根据反馈继续推进。
- Context、Tool、Observation、Action、Permission、Artifact、Gate、Reviewer 和反馈循环都是产品核心。
- 确定性控制面负责状态、Gate、权限、预算、幂等和审计，为 Agent 自主行动提供安全边界；模型不能自由修改业务状态。
- 不得把产品降级为“固定表单或 CRUD 工作流 + AI 聊天框”。完成标准是真实跑通：理解 → 行动 → 产物 → 审查 → 修订或恢复。

开始前完整读取：
1. AGENTS.md
2. README.md
3. docs/handoff.md
4. docs/environments.md
5. docs/HANDOFF_PROMPT.md
6. docs/PRD.md
7. 产品工厂Agent/spec/README.md
8. 产品工厂Agent/spec/Technical-Adaptation.md
9. 产品工厂Agent/spec/Engineering-Schedule.md
10. 产品工厂Agent/spec/Acceptance-Test-Plan.md

然后核验：
- 当前代码和全部 Git 修改；工作区当前尚未形成可依赖的普通 Git tracked 基线，不得 reset、清空或重新初始化。
- 内部与用户 PostgreSQL 的真实数据和隔离边界。
- Alembic migration/head。
- Web、Python、PostgreSQL 测试和 production build。
- 内部环境真实 URL、页面、健康检查、日志和认证。
- GitHub Connector 远端 head 与 Draft PR；远端写入前必须重新核验。

当前真实状态：
- 销售复盘 Agent 为 seed_beta / Context v10 / iteration v1，处于第 9/12 阶段“种子用户内测”。
- G0–G5 已由用户批准；G6 尚未打开。
- 后端开发、前端开发、MVP、内部验收和 Beta Candidate 已完成。
- Builder/Codex、DeepSeek、博查、AG-UI/SSE、认证强制执行、真实用户和项目归属均有真实证据。
- 最新自动化验证：Web 26/26、Python 86/86、PostgreSQL 48/48、production build 通过、Alembic 20260823_0010 (head)。项目软删除、用户隔离回收箱、幂等恢复、删除/恢复审计和 API Key 设置已通过真实测试；保留 1 条 Starlette/httpx 弃用警告。
- 内部环境最近一次健康检查通过：Web http://127.0.0.1:3200，API http://127.0.0.1:8200。
- 当前内部与用户环境均绑定发布包 20260823T155102Z。
- 用户数据库已迁移到 20260823_0010；Secret Store、备份恢复和 095514Z ↔ 155102Z 双向回滚验收通过，最终保持新包。

当前 Web 结构：
- `/` 是独立首页，不显示项目列表。
- `/projects` 是“真实项目”页面，承载项目创建、项目列表和待处理事项。
- `/projects/{projectId}` 是现有 30/70 双栏 Agent 工作区。
- `/settings` 只保留用户 API Key 管理。
- 顶部导航顺序是“首页 / 项目列表 / 设置”；“个人信息”承载用户、角色、用户 ID、运行模式、Session、安全说明和退出登录。
- 邀请码登录成功后统一打开 `/` 首页；普通用户个人信息显示角色“用户”和“用户工作空间”。
- “去处理”和“继续项目”尺寸一致、文字居中。
- 首次引导只在首次登录首页自动出现，并提示用户配置自己的 API。

用户模型 API 当前实现：
- 用户可添加、替换、删除自己的 API Key，并配置接口名称、HTTPS Base URL 和模型名。
- Runtime 按当前项目 owner 使用用户配置，不再把普通用户固定到 DeepSeek。
- 当前真实支持边界是 OpenAI-compatible API，不得虚报支持所有厂商私有协议。
- Key 原文只进入分环境、分用户、权限为 0600 的 Secret Store；PostgreSQL 只保存 SecretRef、指纹、脱敏尾号和非敏感接口元数据。
- HTTP、本机和直接内网 IP 的模型地址会被拒绝；普通用户未配置时 fail closed；本地 DEEPSEEK_API_KEY 只允许内部验证账号测试回退。
- 任意第三方兼容服务的真实模型效果仍需用用户提供的有效 Key 做真实任务验证。

两套独立环境：
- 内部验证环境：3200/8200，保留销售复盘 Agent 与内部验收数据。
- 独立用户环境：3300/8300，独立数据库、Artifact、Workspace、日志、用户 Secret Store、Session Secret 和邀请码；首次登录项目为空。
- 两套环境不能共享业务数据或秘密。
- 任何新版本必须先在内部环境完成迁移、测试、build、健康和用户浏览器验收，再迁移并绑定到用户环境。
- 用户已明确确认本次内部浏览器验收通过；不得把该确认扩大解释为 G6 批准。
- 用户环境已经可用于受控种子内测，但不得伪造真实用户、任务或反馈数据。

下一步顺序：
1. 邀请真实种子用户，用真实任务开展内测；收集成功、失败、使用和反馈数据，不得伪造。
2. 验证 Reviewer 已知问题、真实 429、博查费用/账单、来源质量和第三方 OpenAI-compatible 模型效果。
3. 证据达到退出阈值后生成 BRD / 商业模式确认并打开 G6。
4. 等待用户决定 G6；G6 批准后才正式发布 / 交接。
5. 收集发布后数据与反馈，创建下一轮迭代。

固定边界：
- Gate 只能由用户批准，Agent 不得代批。
- G6 前不得正式发布。
- 前端现有其他内容默认固定；确需修改必须提前告诉用户。
- 不修改冻结的 4 份 Agent Prompt。
- 不使用 mock、删测试、隐藏错误或降低验收标准。
- 不拆 Runtime、后端、前端任务线，不等待并线。
- Builder 不得自动 push、deploy 或删除工作区。
- GitHub 只能使用 Connector；写入前重新核验 head，使用 force:false，不得使用 gh。
- AG-UI/SSE 是事件主通道；2500ms cursor 轮询只能在断线时降级，恢复后停止。
- 认证、用户归属和资源隔离必须 fail closed；不得由前端 owner 参数代替后端 Session 身份。
- 不得泄露或复制邀请码、Session Secret、API Key、内部项目或本机敏感路径。

最终汇报只需简单说明：
1. 当前阶段。
2. 完成了什么。
3. 真实验证结果。
4. 当前等待哪个 Gate 或用户验收。
5. 后面还剩哪些流程。
6. 哪些事项仍未完成。
```

## 当前边界摘要

- 当前不是等待 G5；G5 已批准，G6 尚未打开。
- 当前用户环境已就绪，下一步是开展真实种子用户任务并收集证据。
- 本次用户 API 支持不同 OpenAI-compatible 模型，不等于支持所有私有协议。
- 没有真实种子用户数据前，不得生成已确认的商业结论。
- G6 未批准前不得正式发布。
