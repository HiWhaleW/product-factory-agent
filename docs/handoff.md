# 产品工厂 Agent - 当前交接

> 日期：2026-08-23  
> 当前阶段：第 9/12 阶段“种子用户内测”  
> 项目状态：`seed_beta / Context v10 / iteration v1`  
> 当前闸口：G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a` 已由用户批准；G6 尚未打开

## 一句话结论

销售复盘 Agent 已完成 G0–G5 并进入种子用户内测。用户已确认内部浏览器验收通过；同一已验收发布包 `20260823T155102Z` 已绑定独立用户环境，数据库迁移、Secret Store、恢复和跨版本回滚验收通过。下一步使用真实种子用户和真实任务开展内测；G6 前不得正式发布。

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
- 数据库已引入真实 `users`、邀请码和项目所有者；项目、产物、任务、Run、Gate、Permission 均按当前 Session 用户隔离。
- `/` 已成为独立首页，`/projects` 是真实项目列表页；顶部导航为“首页 / 项目列表 / 设置”，顶部“个人信息”承载原用户与会话内容。
- “真实项目”已增加受控软删除：项目名二次确认、Session owner 校验、活跃 Run 阻断、删除事件审计；顶栏无效“帮助”、`?` 快捷键和虚假快捷键说明已移除。
- `/projects` 已增加用户隔离回收箱；可恢复到删除前阶段，重复恢复幂等，恢复写入 `project.restored`，不提供永久删除。
- 邀请码登录成功后统一 `replace` 到 `/` 首页；普通用户“个人信息”显示其显示名、角色“用户”、用户 ID、用户工作空间和后端 Session 状态。
- `/projects` 的“去处理”和“继续项目”已统一尺寸并居中：桌面 `88×44px`，移动 `157.5×44px`。
- 设置页只保留 API 配置：用户可添加、替换和删除专属 Key，并配置 OpenAI-compatible HTTPS Base URL 与模型名；首次引导仍提示先配置 API。
- Key 原文只存于用户隔离、权限为 `0600` 的受控文件；数据库和 API 只保存/返回脱敏元数据与非敏感接口配置。Runtime 优先使用项目 owner 的配置，普通用户未配置时 fail closed；本地环境变量 Key 只允许内部管理员测试回退。

## 最新验证

| 验证 | 结果 |
|---|---|
| Web | 26/26 |
| Python | 86/86 |
| PostgreSQL 集成 | 48/48 |
| Production build | 通过 |
| Alembic | `20260823_0010 (head)` |
| 浏览器 | 本次 `/projects` 已在真实桌面与 `390×844` 下验证；用户已确认内部验收通过。用户环境未登录首页桌面/移动渲染正常、无 error；登录后体验留给用户本人最终确认 |

保留 1 条 Starlette/httpx 弃用警告。AG-UI/SSE 是主通道；`2500ms` cursor 轮询只在断线时降级，恢复后自动停止。生产环境必须配置并开启 HttpOnly Session 认证，否则 API 拒绝启动。

## 当前不能做

- 用户环境已可用于受控种子内测；只能收集真实任务、成功、失败、使用和反馈数据，不得伪造。
- 没有真实内测数据前不得生成“已确认”的商业结论。
- G6 未批准前不得正式发布。
- 前端非必要不动；确需修改必须提前告诉用户。
- 不修改冻结的 4 份 Agent Prompt。
- 不使用 mock、删测试或隐藏错误放行。

## 后续流程

1. 使用真实种子用户和真实任务开展内测，收集成功、失败、使用和反馈数据。
2. 验证 Reviewer 已知问题、真实 429、博查费用/账单、来源质量和第三方兼容模型效果。
3. 达到真实样本、任务成功和反馈阈值后，生成 BRD / 商业模式确认并打开 G6。
4. 用户决定 G6；批准后发布 / 交接，再收集反馈进入下一轮迭代。

## 项目和两套环境

- 真实项目 ID：`2a3c38e1-9704-4f83-a096-84cb5a5025e7`。

| 项目 | 内部验证环境 | 独立用户环境 |
|---|---|---|
| 用途 | 验证销售复盘 Agent 的开发全流程 | 供真实种子用户创建自己的项目 |
| Web / API | `127.0.0.1:3200` / `127.0.0.1:8200` | `127.0.0.1:3300` / `127.0.0.1:8300` |
| 数据 | 保留销售复盘 Agent 与内部验收数据 | 独立数据库；首次登录项目为空 |
| 运行目录 | `.runtime/seed-beta/` | `.runtime/user-beta/` |
| 健康检查 | `scripts/seed-beta/health-check.sh` | `scripts/user-beta/health-check.sh` |

内部与用户环境当前均绑定 `20260823T155102Z`；用户数据库为 `20260823_0010`。两套环境的数据库、Artifact、Workspace、用户 Secret Store、日志、Session Secret 和邀请码互相独立。详细说明见 [双环境运行说明](./environments.html)。

最新真实核验：用户 Web/API 健康检查通过，首次登录项目为空且内部项目数为 0；Secret Store 临时 Key 添加、响应脱敏、`0600` 权限、删除无残留通过；迁移后备份恢复到隔离临时库通过；`095514Z ↔ 155102Z` 双向回滚通过并最终恢复到新包。

- 可回收测试 fixture：`c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001`，不得冒充真实业务项目。
- GitHub：`HiWhaleW/product-factory-agent`，`codex/initial-import`，Draft PR #1；任何远端写入前用 Connector 重新核验 head，禁止 `gh` 和 force push。

## 仍未完成

- 真实种子用户任务、使用和反馈数据。
- 用户环境登录后的首页、项目空态、设置页和普通用户个人信息仍需由用户本人做最终浏览器体验确认；自动化登录、隔离和未登录桌面/移动页面已通过。
- Factory Lead 尚无确定性 feasibility/preflight 分类器；当前只能依赖模型澄清和 Run 预算上限，不能保证在第一次模型调用前识别所有绝对不可能目标。
- BRD/G6、正式发布/交接、数据与反馈。
- 当前用户入口仍是本机 URL；公网域名、HTTPS 和外部可访问部署尚未完成。
- 用户环境 current 为 `20260823T155102Z`、previous 为 `20260823T095514Z`；真实双向回滚已通过，最终保持新包。
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
