# 产品工厂 Agent - 阶段交接

> 交接日期：2026-08-23  
> 当前阶段：产品状态 `prd / Context v3 / iteration v1`；真实 PRD/Review 已保存，G2 open  
> 下一闸口：等待用户人工决定 G2  
> 开发状态：AI PM PRD 与 Reviewer 已真实运行；G2 未决定，Builder 未启动  
> 执行方式：后续不再拆分 Runtime、后端和前端并线，由同一任务在当前工作区端到端闭环

## 1. 交接结论

产品工厂 Agent 的产品边界、交互、共享上下文、状态/人工闸、能力/工具权限、技术适配、测试方法、竞品/GitHub 参考和 4 个核心 Agent Prompt 已经形成可执行规格。

四项 V1 Spec Freeze 已于 2026-08-20 获用户明确批准。D3–D4 已于 2026-08-21 收口。销售复盘 Agent 已从 G0/G1 继续真实运行到 PRD：AI PM Run `9c7ffc14…` 生成 PRD v1，Reviewer Run `6442a2fa…` 返回 `pass` 并生成 PRD Review v1，确定性服务只打开 G2 `fdac9cd1…`，没有代批。项目仍为 `prd / Context v3 / iteration v1`。完整脱敏证据见 [HTML](./evidence/d5-prd-runtime-progress-2026-08-23.html) / [JSON](./evidence/d5-prd-runtime-flow-2026-08-23.json)。AG-UI/SSE 仍未完成。

交互事实必须单独说明：唯一权威视觉基线仍是根目录 `产品工厂Agent_Harness表.html`。当前 Web 已移除 `demoProject`，在同一个 Next.js 应用中统一 `/` 首页、`/projects/{projectId}` 双栏工作区和 `/settings` 设置/运行状态页；实现真实项目创建/列表、消息输入、参与者区、Event cursor 短轮询、React Flow Artifact DAG、受控内容预览/下载，以及 Gate/Permission 独立卡片。

2026-08-22 已用 ego-lite 在生产模式完成桌面 `1440×900` 与移动 `390×844` 的统一导航和核心交互 QA，并归档真实截图与 JSON。当前确认稿中：桌面工作区为用户最新确认的约 `30/70` 双栏；12 阶段仍为 `6×2`，移动仍使用“群聊 / 产物”同屏切换；工作区顶部“事件同步：cursor 短轮询 · 降级方案”可见标签已删除；Gate/Permission 卡常驻细黑边但整卡不做 hover 位移，卡内按钮保留 MotherDuck 式动效；Artifact 节点固定 `168×190px`、常驻细黑边并保留 hover 承托；参与者默认无黑框、hover 出框，“用户”可见文案改为“我”。用户已明确当前前端没有问题，`design-qa.md` 为 `passed`；这只代表当前确认稿和已测试范围通过，不是视觉永久冻结或完整产品验收完成。底层 `2500ms` cursor 短轮询仍是 AG-UI/SSE 未完成前的降级方案，删除标签不代表传输层完成。

GitHub 安全快照已通过 Connector 完成：私有仓库 `HiWhaleW/product-factory-agent` 默认分支为 `main`；`codex/initial-import` 从精确父提交 `36503fd9…` 以 `force:false` 快进到实现提交 [`db39b5dd…`](https://github.com/HiWhaleW/product-factory-agent/commit/db39b5ddfa01e17477c99c6eaa512c5f23422c30)；[Draft PR #1](https://github.com/HiWhaleW/product-factory-agent/pull/1) 仍为 open/draft。全程未使用 `gh` 或本地 Git push。31 个上传文件、排除清单和扫描证据见 [Markdown](./evidence/github-safe-snapshot-2026-08-23.md) / [HTML](./evidence/github-safe-snapshot-2026-08-23.html)。

本次接手任务继续完成了真实 PRD 切片：严格 PRD/Review Schema、AI PM 与 Reviewer Run、确定性 Artifact/ToolRun/RunStep/Event 持久化、G2 只开不批，以及可回收 Gate/Permission 联合验收 fixture。第一次模型 Run 因缺少必填状态被提交接口拒绝，未创建 Artifact/G2；修正 Schema 后重新真实运行成功。

## 2. 已完成

### 产品与交互

- 4 个核心 Agent：Factory Lead、AI PM、Builder、Reviewer。
- 原 17 岗位收敛为 4 Agent + Skill/能力包；动态升格条件已定义。
- 用户于 2026-08-20 修订为 12 个本轮阶段 + 下一轮迭代循环；分阶段开发固定后端 → 前端。
- G0-G6 改为 7 个必审闸；全局规则回写改用独立 Governance Review。
- 根目录 Harness 仍是权威交互视觉基线；其历史比例为 38/62。当前实现按用户最新明确确认采用约 30/70，左侧团队群聊、右侧累计产物画布的交互范式不变。
- 子目录 Harness 页面已同步 12 阶段生命周期，但它只是生命周期适配投影，不替代根目录视觉基线。
- 新 Agent 入群旁白、自我介绍、Context Pack 交接和 `@Agent` 路由。
- Markdown/代码/URL/闸/反馈节点操作和上线反馈→v1.1 分支。

### Harness 与架构

- 五层上下文、版本化 Context Pack、AgentHandoff、VerifiedFact/Assumption/GateDecision。
- 确定性项目状态机、RunState、人工闸、条件触发器、幂等和恢复规则。
- 12 个能力契约、V1 工具白名单、Codex CLI 受限工作区、预算和 Secret/审计策略。
- 参考 `learn-claude-code-main` 新主线 s01-s17 完成 Harness 机制审计；补充 Artifact/Execution 双 DAG、Run Journal、三态权限、上下文压缩、后台回注和有界完成判定。
- Next.js/CopilotKit/AG-UI/React Flow + FastAPI/LangGraph/PostgreSQL + Codex CLI Adapter 技术适配。
- 已记录当前可提供模型为 DeepSeek；V1 不做向量 RAG，使用有界 Agent Loop，LangGraph 只负责 Agent Run 编排/暂停/恢复。
- API、数据实体、事件、环境变量和内部部署目标契约。
- D5 确定性定义链路底座：版本化 Project Brief、幂等澄清、精确 Context Pack、G0/G1 状态转移、AgentMembership、定义产物提交和 cursor Event API；这不是 AG-UI/SSE。
- DeepSeek 异步 Adapter：SecretRef、认证错误脱敏、结构化输出、工具调用、SSE、超时、429 和上下文过长类型化；真实冒烟证据见 [Markdown](./evidence/d5-deepseek-smoke-2026-08-22.md) / [HTML](./evidence/d5-deepseek-smoke-2026-08-22.html)。
- D5 Agent Runtime：4 Agent 冻结注册、D5 角色激活边界、`model → policy → finish` 有界 LangGraph、`allow/ask/deny`、持久化 checkpoint、跨 Service 恢复、副作用对账与 cursor Event。脱敏台账见 [HTML](./evidence/d5-agent-runtime-progress-2026-08-22.html) / [JSON](./evidence/d5-runtime-smoke-2026-08-22.json)。
- PRD Runtime：AI PM 与 Reviewer 各 1 turn / 0 retry；PRD/Review 通过 `artifact_store` 确定性保存，Tool Policy 为 `allow`，幂等键和副作用确认已写 Journal；事件 sequence `67–82` 可按 cursor 恢复。
- Factory Lead 对齐服务：ContextVersion bootstrap Pack、结构化澄清/Brief Schema、调用前幂等占位、并发双击去重、Agent 消息/Brief/G0 确定性落库；模型不能批准 G0 或推进项目状态。
- 6 层放行、6 个核心 E2E、真模型冒烟、浏览器、安全和 D10 判定。

### 调研与 Prompt

- 最接近直接竞品 Atoms（原 MGX）；Replit Agent、Lovable、Bolt、v0 为直接替代。
- LangGraph、React Flow、CopilotKit + AG-UI 决定 V1 采用；OpenHands/MetaGPT/ChatDev/E2B 等作参考。
- GPT Pilot 因官方披露供应链恶意代码且已停止维护，明确禁止作代码依赖/克隆来源。
- Factory Lead、AI PM、Builder、Reviewer Prompt v0.2 已冻结；Factory Lead / Reviewer 已真实运行，但不能由此推定 4 Agent 整体效果通过。

### 文档和可视化

- 11 份核心产品/执行/排期规格、3 份研究/缺口/参考评估报告、4 份 Prompt。
- 已补齐独立前端实施规格：三页面线框、组件树、事件投影、全状态、响应式、DAG 规模策略和 D3-D8 每日退出证据。
- D1-D2 规格、Harness 参考评估、工程排期和交互概念 HTML。
- D1-D2 规格语义一致性已归档；浏览器/交互证据已从规格结论中拆开，见 [Markdown](./evidence/d1-d2-consistency-revalidation.md) / [HTML](./evidence/d1-d2-consistency-revalidation.html)。

## 3. 尚未完成

- D5/D6 当前真实链路已到 G2 open；G2 尚未由用户决定，因此不能进入方案确认。
- AI PM 最终 Run 使用 1 次博查、3 次有界模型尝试（2 次 schema retry）；Reviewer 使用 2 次尝试（1 次 schema retry）。失败正文未记录，仅保留状态、Hash、Token、Journal 和错误码。
- Codex CLI Adapter 完整 Builder 执行和真实受限项目工作区；当前只有 `--version` 只读 smoke。
- CopilotKit/AG-UI 流式事件；当前使用带 cursor 的短轮询降级。
- 可回收 Gate/Permission 数据 fixture 已存在；前端真实浏览器联合验收尚未完成。真实业务 G2 不用于破坏性验收。
- 当前项目的 Builder Membership/Run 与完整 Runtime 群聊生成；现有人工消息不能冒充 Agent 生成。
- 用户已确认当前前端无问题；若后续再有视觉标注，仅做增量修改并复验，不得借机重设计已认可交互流程。
- 真实 429 未观察；配置名 `deepseek-chat` 当前观察到服务端响应名 `deepseek-v4-flash`；Provider 返回 Token 但不返回 cost，Runtime 不伪造费用。
- AG-UI 长连接、真实浏览器 pause/resume 联合验收和完整模型质量人工评审仍未完成。
- 认证强制执行、内网发布、PostgreSQL/Artifact 备份恢复和真实 URL；Session 契约存在，但 `auth_enforced=false`。
- 第一个企业内部 dogfood 项目与效率/质量数据。

## 3.1 当前可重复验证的证据

- 2026-08-23 PostgreSQL `16.15` 在线，migration 已到 `20260822_0006 (head)`；`0005` 补充 Web 投影契约，`0006` 回填真实 ToolRun/recovery 事件。
- `pnpm test:api:integration`：44/44 通过；在既有 D5 集成覆盖上新增 PRD 提交、clean-review 和 G2 只开一次且不推进项目/不启动 Builder 的确定性验证。
- 2026-08-23 当前统一工作区 `pnpm check` 已重新通过：Web 13/13、Python 60 passed、Ruff/ESLint/TypeScript 通过；不存在“等待并行 Runtime 线修复”的当前阻塞。
- Factory Lead 真实对齐：两轮均 1 turn / 0 retry，共 6,633 Token；requested `deepseek-chat`、observed `deepseek-v4-flash`，完成后 `waiting_g0`。证据：[HTML](./evidence/d5-factory-lead-alignment-smoke-2026-08-22.html)。
- Agent 测试 33/33；DeepSeek 真实冒烟 7 项通过、1 项未观察。虚拟产品 AI PM / Reviewer / G1 批准脱敏证据：[JSON](./evidence/d5-sales-retrospective-product-flow-2026-08-22.json) / [Runtime](./evidence/d5-agent-runtime-progress-2026-08-22.html)。
- 真实 PRD：AI PM `9c7ffc14…`、Reviewer `6442a2fa…`、PRD `71d3b81a…` v1、Review `44c79e5a…` v1、G2 `fdac9cd1…` open；证据见 [HTML](./evidence/d5-prd-runtime-progress-2026-08-23.html)。
- 2026-08-22 使用 ego-lite 检查本轮更新的 README、handoff、HANDOFF_PROMPT、operator-runbook、product-lifecycle 和 materials-inventory HTML：`1440×900` / `390×844` 均无页面级横向溢出；正式交接提示词的标题、三项任务和内部导航可见。该结果不替代产品 Web 视觉 QA。
- Web ESLint、TypeScript、Vitest 13/13、Ruff 和 Python 单测 60/60 通过；PostgreSQL 集成测试默认显式跳过，须用上一命令单独运行。
- `pnpm build`：Next.js 16.3.1 production build 通过，`/`、`/projects/[projectId]`、`/settings` 和同源 API proxy 均生成。
- ego-lite 生产模式：`1440×900` 使用用户最新确认的约 30/70 双栏，`390×844` 在同一屏切换群聊/产物，工作区均无页面级滚动；首页、工作区、设置页统一导航通过，Console 应用错误为 0。
- 交互证据：Artifact 节点真实拖动仅改变本地 React Flow 视图，桌面/移动真实内容预览通过；Gate 整卡静止、卡内按钮 hover 通过；参与者 hover 与“我”文案通过；不存在项目的真实 404 错误态通过。当前已提供可回收开放 PermissionRequest 数据 fixture，浏览器联合验收仍待执行。
- 前端证据入口：[Design QA Markdown](../design-qa.md) / [HTML](../design-qa.html) / [本轮 ego-lite JSON](./evidence/d5-runtime-projection-ego-qa-2026-08-22.json)。本轮截图接口超时，未把历史图片冒充新证据；既有统一链路截图仍保留原始日期与用途。
- D3–D4 收口证据：[Markdown](./evidence/d3-d4-closure-2026-08-21.md) / [HTML](./evidence/d3-d4-closure-2026-08-21.html)。

- 历史截图：[应用桌面](./evidence/app-desktop.png)、[应用移动](./evidence/app-mobile.png)、[生命周期桌面](./evidence/lifecycle-desktop.png)、[生命周期移动](./evidence/lifecycle-mobile.png)、[Harness 移动](./evidence/harness-mobile.png)。这些图片来自不同 mock/原型页面，只能作为历史快照，不能证明权威交互符合性。
- D1-D2 规格一致性复验：4 Agent、12 阶段循环、后端→前端、G0-G6、Context Pack、Artifact/Execution 双 DAG 与控制面分离通过；浏览器交互保持未验收。归档：[Markdown](./evidence/d1-d2-consistency-revalidation.md) / [HTML](./evidence/d1-d2-consistency-revalidation.html)。
- 当前事实审计：[Markdown](./evidence/implementation-truth-audit.md) / [HTML](./evidence/implementation-truth-audit.html)。

## 4. Spec Freeze Review 批准记录

- [x] V1 仅单用户/单管理员。
- [x] V1 仅 DeepSeek 一个模型供应商；接入渠道、模型名和 Base URL 最晚 D5 真模型切片前锁定并冒烟。
- [x] V1 Builder 使用本地 Codex CLI 适配器。
- [x] V1 本机/内网运行，不实现企业 SSO、多租户或云代码沙箱。

批准记录已同步到 `产品工厂Agent/spec/README.md` 和 `docs/PRD.md`；D3–D4 已收口，D5 正在进行。

## 5. 下一位接手者必须完成的三件事

### 5.1 使用 GitHub 插件推送当前安全快照

1. 只能使用 GitHub 插件/Connector 完成远端读取、分支、文件上传/提交和 PR 更新；不得使用 `gh` CLI。
2. Connector 已核验默认分支、`codex/initial-import` 和 Draft PR #1；推送前必须再次确认 PR head 仍等于预期父提交，避免覆盖并线更新。
3. 推送前按 `.gitignore` 和秘密扫描形成安全清单。不得上传 `.env`、`.runtime/`、`.venv/`、`node_modules/`、`.next/`、Artifact/Workspace、缓存、SecretRef 原值、本机来源路径或其他敏感文件。
4. 不得 force push、重建仓库、覆盖远端其他任务线或把所有未跟踪文件不经审查地整包提交。
5. 插件未安装、不可调用或无写权限时，停止远端写入并请求安装/授权；不得回退使用 `gh`。
6. 完成后在交接中记录真实 repo、分支、commit/PR 链接、上传清单、排除清单和插件证据。

### 5.2 当前统一工作区已完成的跨层切片

- 已恢复“销售复盘 Agent”到 Web 同源 PostgreSQL/API；首页与工作区读取真实 Evidence Index v2、MRD v2、Red Team Review v2、历史 G1 及两项结构化 P2。
- 已提供 Artifact 版本索引（version/status/created_at/created_by/content availability）、Project `iteration_version`、Graph owner/created_at、Permission reason/redacted parameters、执行投影和 ToolRun/recovery 回填。
- 已提供 `GET /api/v1/projects/{project_id}/gate-decisions`，前端可直接读取批准人、批准时间、Context 前后版本和目标阶段；完整接口见 [D5 Web / 后端真实投影契约](./contracts/d5-web-backend-projection-contract-2026-08-23.md)。
- 已提供邀请码换取 HttpOnly 签名 Session、`/me` 与 logout 契约；当前未配置认证且请求强制执行仍为 `false`，不得写成登录完成。
- 仍缺 streaming/AG-UI/SSE、可回收 fixture 的真实浏览器联合验收、认证强制执行和完整真实群聊生成。真实业务 Gate 不得用于破坏性验收或由 Agent 代批。
- `2500ms` cursor 短轮询仍是 AG-UI/SSE 未完成前的降级方案；用户只要求删除可见标签，不代表 transport 已修复。
- 不得再使用“D3 双栏交互验收”作为 D5 业务验收项目；它只能用于前端组件回归。
- Project `iteration_version`、Graph owner/agent、`created_at`、登录/Session、`/me`、logout 和过期原因契约已对齐；当前剩余的是认证配置与请求强制执行，不是字段缺失。

### 5.3 后续开发安排

1. [已完成] 使用 GitHub Connector 完成当前安全快照、远端分支和 PR 状态核验。
2. [已完成] Runtime/后端统一当前项目真相源，把“销售复盘 Agent”恢复到 Web 同源 API。
3. [已完成] 前端真实项目接入验收：Evidence Index v2、MRD v2、Red Team Review v2、G1 两项 known issues 和 Artifact v1/v2 版本索引。
4. [已完成] 真实 AI PM PRD、确定性提交、Reviewer clean-review、PRD/Review Artifact 与 G2 open；G2 未决定。
5. 等待用户决定 G2；批准后推进方案/G3、技术栈/G4，G4 前不得启动 Builder。
6. G4 后按后端开发 → 前端开发的独立 Execution Task、AgentRun、RunStep、测试和 ArtifactVersion 证据推进。
7. 完成 MVP、内部验收/G5、种子内测、商业 BRD/G6、发布/交接和反馈迭代。
8. 在同一任务线按优先级完成 fixture 的前端联合验收，并补齐 AG-UI/SSE、断线恢复和身份认证强制执行；每次跨层改动同步 API、Web、测试、文档和浏览器证据。

## 6. D3-D4 历史执行顺序

1. 读 `README.md`、`AGENTS.md`、本文、spec README/PRD/Technical Adaptation。
2. 完成 Spec Freeze Review，未通过不写应用代码。
3. 保存当前素材后初始化 Git，不删、不移动原始手册和 HTML。
4. 用 uv 创建 Python 3.12 环境；创建 Next.js/FastAPI monorepo 和 lockfile。
5. 配置 PostgreSQL 地址、Artifact/Workspace 根目录和本地安全边界。
6. 实现最小实体/API：Project、Message、Event、ContextVersion/Pack、Artifact/Version/Edge、Gate/Decision，以及 Task/Dependency、Run/Step、Permission 控制面。
7. 实现状态迁移、三态权限、任务原子认领、人工闸、幂等和副作用恢复单测。
8. 已将静态 mock 改为真实 API/Event/Gate/Permission 投影，并按根目录权威基线实现团队群聊 + Artifact 画布；模型未接入状态继续明确展示，不能伪装真模型。
9. 更新根 README/AGENTS 和 docs 中的真实命令、API、表、环境变量与完成状态。

## 7. 关键风险

| 风险 | 反方问题 | 应对 |
|---|---|---|
| DeepSeek 接入差异 | 配置名与响应模型名为何不同？真实 429 如何验证？ | 每个 Run 同时记录 requested/observed model；保留 429 未观察状态，只宣称分类与有限重试单测通过 |
| AI PM/Reviewer 对齐 | Agent Runtime 下一步调用什么？ | 用 `DefinitionSubmissionCreate` 提交 AI PM 结果；Reviewer 只读 `definition-review/v1` candidates；用 `DefinitionReviewCreate` 提交红队结果，不能直接写 Gate/Project |
| 竞品高度重合 | Atoms/Replit/Lovable 是否已足够？ | 用 dogfood 验证“企业审计 + 产品证据闸 + 累计 DAG”是否有价值 |
| 多 Agent 表演化 | 是否只增加 Token 和沟通噪声？ | 只 4 核心 Agent；其他为 Skill；跟踪协调成本 |
| 画布“意大利面” | 100 节点后是否无法理解？ | 阶段子图、筛选、局部重跑和 25/100 节点验收 |
| 本地 Builder 风险 | Codex 是否越工作区/泄密？ | 路径/软链接/Secret 测试、确定性 Tool Policy；V2 沙箱 |
| 人工闸过多 | 7 个必审闸是否拖慢十日交付？ | 方案与技术栈分开确认但合并准备材料；记录停留时间，用真实返工率决定后续是否合并 |
| 教学 Harness 被误当依赖 | 是否直接复制 shell/线程/文件状态实现？ | 只采用机制；拒绝 `shell=True`、字符串黑名单、终端审批和内存唯一状态 |

## 7. 交接完整性

- 全量素材：[materials-inventory.md](./materials-inventory.md)
- 架构：[architecture.md](./architecture.md)
- 环境/运维：[operator-runbook.md](./operator-runbook.md)
- 工程排期：[Engineering-Schedule.html](../产品工厂Agent/spec/Engineering-Schedule.html)
- 交接提示词：[HANDOFF_PROMPT.md](./HANDOFF_PROMPT.md)
- 可视化交接：[handoff.html](./handoff.html)
- Harness 参考评估：[Harness-Reference-Assessment.html](../产品工厂Agent/spec/Harness-Reference-Assessment.html)
