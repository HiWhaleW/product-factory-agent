# 产品工厂 Agent - 正式交接提示词

> 平台：产品工厂 Agent，下一步为 GitHub 更新 → 火山引擎 `user-beta`  
> 内部示范项目：销售复盘 Agent，`seed_beta / Context v10 / iteration v1`；G5 已批准，G6 尚未打开  
> 内部 current / previous：`20260824T074916Z` / `20260824T042123Z`；用户 current / previous：`20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`  
> 交接下一步：GitHub Connector 更新 → 火山引擎账号/拓扑/费用预检 → 用户确认后部署并验收 `user-beta`；本机用户环境绑定/重验是独立放行线

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
5. docs/cloud-user-beta-handoff.md
6. docs/HANDOFF_PROMPT.md
7. docs/PRD.md
8. 产品工厂Agent/spec/README.md
9. 产品工厂Agent/spec/Technical-Adaptation.md
10. 产品工厂Agent/spec/Engineering-Schedule.md
11. 产品工厂Agent/spec/Acceptance-Test-Plan.md

然后核验：
- 当前代码和全部 Git 修改；工作区当前尚未形成可依赖的普通 Git tracked 基线，不得 reset、清空或重新初始化。
- 内部与用户 PostgreSQL 的真实数据和隔离边界。
- Alembic migration/head。
- Web、Python、PostgreSQL 测试和 production build。
- 内部环境真实 URL、页面、健康检查、日志和认证。
- GitHub Connector 远端 head 与 Draft PR；远端写入前必须重新核验。

当前真实状态：
- 必须区分三个对象：销售复盘 Agent 是内部示范项目；产品工厂 Agent 是平台产品本身；火山引擎 user-beta 是给真实用户测试平台的环境。
- 销售复盘 Agent 为 seed_beta / Context v10 / iteration v1，处于第 9/12 阶段“种子用户内测”。
- 销售复盘 Agent 的 G0–G5 已由用户批准；该示范项目 G6 尚未打开。
- 产品工厂 Agent 平台下一步是更新 GitHub，再部署火山引擎 user-beta；这两步不需要先批准销售复盘 Agent G6。
- 后端开发、前端开发、MVP、内部验收和 Beta Candidate 已完成。
- Builder/Codex、DeepSeek、博查、AG-UI/SSE、认证强制执行、真实用户和项目归属均有真实证据。
- 最新自动化验证：Web 34/34、Python 94/94（48 skipped）、PostgreSQL 48/48，production build、ESLint、TypeScript、Ruff 通过，Alembic 20260823_0010 (head)。内部 standalone 包 20260824T074916Z 的 SHA-256 manifest 在启动前后不变，4 份冻结 Prompt 哈希未变；保留 1 条 Starlette/httpx 弃用警告。
- 内部环境最近一次健康检查通过：Web http://127.0.0.1:3200，API http://127.0.0.1:8200。
- 当前内部 current / previous 为 20260824T074916Z / 20260824T042123Z；用户环境 current / previous 仍为 20260824T042412Z-identity-only / 20260824T032335Z-settings-only，尚未绑定或重新验收 074916Z。
- 用户数据库已迁移到 20260823_0010；Secret Store、备份恢复和本机回滚边界验收通过。当前 current 为 20260824T042412Z-identity-only，previous 为 20260824T032335Z-settings-only。
- 2026-08-24 最新即时核验时，本机 3200/8200/3300/8300 均在监听，健康、未登录 401、Session 与安全响应头通过；进程状态可能随运维动作变化，后续仍须实时核验，不能只引用历史结果。

当前 Web 结构：
- `/` 是独立首页，不显示项目列表。
- `/projects` 是“真实项目”页面，承载项目创建、项目列表和待处理事项。
- `/projects/{projectId}` 是现有 30/70 双栏 Agent 工作区。
- `/settings` 只保留用户 API Key 管理。
- 顶部导航顺序是“首页 / 项目列表 / 设置”；“个人信息”只显示名称、账号身份、登录状态和退出登录，不显示用户 ID、运行模式或 Session/认证诊断。
- 邀请码登录成功后统一打开 `/` 首页；内部显示“管理员账号”，用户端显示“种子用户”。
- “去处理”和“继续项目”尺寸一致、文字居中。
- 首次引导在登录首页自动出现，按真实用户 ID 独立记录；只有明确跳过或完成后才标记已看，并提示用户配置自己的 API。

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
- 本机用户环境的任何换包必须先在内部环境完成迁移、测试、build、健康和用户浏览器验收，再单独迁移、绑定和重验；本机用户换包不是 GitHub 后火山引擎账号/拓扑/费用预检的前置 Gate。
- 用户已明确确认本次内部浏览器验收通过；不得把该确认扩大解释为 G6 批准。
- 历史用户组合包已通过既有验收，但新内部基线尚未绑定或重验；平台当前只能标记 internal_reproducible_baseline_ready / cloud_preflight_pending，本机用户环境另为 local_user_binding_pending。不得提前标记本机 user_baseline_ready，也不得伪造真实用户、任务或反馈数据。

下一步顺序：
1. 以已完成验证的内部 20260824T074916Z 作为可重现源码/构建基线；确认 manifest 启动前后不变且 4 份冻结 Prompt 哈希未变。不得上传 `.runtime`、手工混合 `.next` 或不可重现发布产物冒充源码。
2. 用 GitHub Connector 只读重新核验 `HiWhaleW/product-factory-agent` Draft PR #1 和 `codex/initial-import` head。当前 2026-08-24 只读快照 head 为 `69eb31d22430522f32c8db6b1151336756f42d01`，但写入前必须再查。
3. 扫描将上传内容中的邀请码、Session Secret、API Key、数据库连接串、日志、备份、用户数据和本机敏感路径；保持 4 份冻结 Agent Prompt 不变。
4. 通过 Connector 创建 blob/tree/commit，使用 `force:false` 更新 `codex/initial-import`；保持 PR 为 Draft，不 merge。写入后反向核验 ref、commit 和 PR。禁止 `gh`、本地 `git push` 和 force push。
5. GitHub 完成后，按 `docs/cloud-user-beta-handoff.md` 执行火山引擎只读预检。先核验账号、地域、网络、网关、数据库、持久化存储、域名/证书、费用和拓扑；付费资源或目标不唯一时停止并请用户决定，不得默认整个项目直接进 veFaaS。
6. 本机独立用户环境继续保留历史组合包；如后续要绑定 074916Z，单独完成 preflight、绑定及首页引导、API 空态、个人信息、项目空态、健康、安全、隔离与 1440x900 / 390x844 浏览器重验。完成前不得标记本机 `user_baseline_ready`，但不阻塞云预检或用户确认后的云部署。
7. 带本地 Codex CLI/工作区能力的 Builder 不得直接暴露到公开 veFaaS 函数。根据官方文档、实际账号资源和真实冒烟确定 Web/API/SSE/长任务、PostgreSQL、Artifact/Workspace、Secret Store 和 Builder 的火山引擎拓扑。
8. 用户确认精确拓扑和费用边界后，才新建独立火山引擎 `user-beta`：PostgreSQL 迁移到 `20260823_0010`，新 Artifact/Workspace、日志、Secret Store、Session Secret 和邀请哈希。不复制本地或内部邀请码、Session Secret、API Key、用户 Secret Store 或内部项目。
9. 完成 HTTPS、`AUTH_ENFORCED=true`、Secure/HttpOnly Session、未登录 401、AG-UI/SSE、空项目隔离、API 凭据空态/添加/删除脱敏、Secret Store、备份/恢复、版本回滚、`1440x900` 和 `390x844` 真实浏览器 QA。通过后只标记平台 `user_beta_ready`，不冒充 production/general availability。
10. 再邀请真实用户，用真实任务收集平台成功、失败、使用和反馈数据。销售复盘 Agent 保持种子内测；若后续要正式发布该示范项目，再以其真实内测证据生成 BRD、打开 G6 并等待用户决定。

固定边界：
- Gate 只能由用户批准，Agent 不得代批。
- 销售复盘 Agent G6 前不得宣布该示范项目正式发布；不得用这条阻塞产品工厂平台 `user-beta` 部署。
- 前端现有其他内容默认固定；确需修改必须提前告诉用户。
- 不修改冻结的 4 份 Agent Prompt。
- 不使用 mock、删测试、隐藏错误或降低验收标准。
- 不拆 Runtime、后端、前端任务线，不等待并线。
- Builder 不得自动 push、deploy 或删除工作区。
- GitHub 只能使用 Connector；写入前重新核验 head，使用 force:false，不得使用 gh。
- 火山引擎上云是产品工厂平台的受控用户测试环境，不需销售复盘 Agent G6，也不等于该示范项目正式发布。
- 需要创建付费云资源、网关、域名/证书、VPC、数据库或存储时，先展示精确目标和费用边界；目标不唯一时停止请用户决定。
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

- 销售复盘 Agent 的 G5 已批准，G6 尚未打开；这不是平台 `user-beta` 的前置 Gate。
- 内部可重现基线已就绪；本机用户环境尚未绑定或重验该包。下一步是 GitHub Connector 更新、火山引擎账号/拓扑/费用预检，再由用户决定精确云资源边界；本机用户绑定/重验是独立放行线，不阻塞云预检。
- 本次用户 API 支持不同 OpenAI-compatible 模型，不等于支持所有私有协议。
- 没有真实种子用户数据前，不得生成已确认的商业结论。
- 未批准销售复盘 Agent G6 时，不得宣布该示范项目正式发布。
