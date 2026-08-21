# 产品工厂 Agent - 阶段交接

> 交接日期：2026-08-22  
> 当前阶段：D5 定义链路进行中；确定性后端底座、DeepSeek Adapter 和有界 LangGraph Runtime 已实现  
> 下一闸口：真实产品项目的 G0 用户决定；隔离 fixture 的 G1 保持 open，不代批  
> 开发状态：AI PM→Reviewer→G1 open 真实纵向冒烟已完成；产品 G0/G1、Builder 和完整 D5 尚未完成

## 1. 交接结论

产品工厂 Agent 的产品边界、交互、共享上下文、状态/人工闸、能力/工具权限、技术适配、测试方法、竞品/GitHub 参考和 4 个核心 Agent Prompt 已经形成可执行规格。

四项 V1 Spec Freeze 已于 2026-08-20 获用户明确批准。D3–D4 已于 2026-08-21 收口。2026-08-22 已完成 D5 Project Brief/澄清/Context 精确绑定/G0-G1/Agent 入群/SSE，以及 AI PM 提交、Reviewer clean-review 输入、Red Team Review 持久化和 G1 open 的确定性契约，PostgreSQL 在线套件为 42 项。真实 Factory Lead 产品项目保持 `alignment / Context v1` 等待 G0。另一个隔离 fixture 已真实完成 `G0 allow → AI PM Permission/checkpoint → 博查 → Evidence/MRD → Reviewer → Red Team Review → G1 open`；G1 未决定，项目未进入 PRD。失败记录包含一次 Reviewer `reject` 和三次 AI PM schema fail-closed，未用 mock 继续。

交互事实必须单独说明：唯一权威视觉基线仍是根目录 `产品工厂Agent_Harness表.html`。当前 Web 已移除 `demoProject`，实现真实项目创建/列表、消息输入、参与者区、Event cursor 短轮询、React Flow Artifact DAG、受控内容预览/下载，以及 Gate/Permission 独立卡片。ego-lite 验证了 `1440×900` 双栏与 `390×844` 同屏切换，工作区无页面级滚动；但原生截图持续超时，根目录 `design-qa.md` 依规则保持 `blocked`，不宣称完整视觉忠实度验收通过。

前端视觉补丁已在 2026-08-22 同步：工作区不需要用户理解的顶部技术信息已删除，画布标题使用真实阶段/Context 动态生成，工作区字号整体增加 `2px`；品牌、头像、事件和 Gate 图片默认不显示黑框，只在 hover / focus-within 时显示。上述修改已通过 ego-lite 计算样式和交互核验，原生截图阻塞仍保留。

GitHub 私有仓库已建立：`https://github.com/HiWhaleW/product-factory-agent`。安全发布分支为 `codex/initial-import`，Draft PR 为 `https://github.com/HiWhaleW/product-factory-agent/pull/1`。远端提交不含 `.env`、Runtime、虚拟环境、依赖、构建缓存、工作区、本机 Alembic 配置、含本机来源路径的冻结/参考原文或大型本地 QA PNG/PDF；Markdown/HTML/JSON 证据摘要保留。

## 2. 已完成

### 产品与交互

- 4 个核心 Agent：Factory Lead、AI PM、Builder、Reviewer。
- 原 17 岗位收敛为 4 Agent + Skill/能力包；动态升格条件已定义。
- 用户于 2026-08-20 修订为 12 个本轮阶段 + 下一轮迭代循环；分阶段开发固定后端 → 前端。
- G0-G6 改为 7 个必审闸；全局规则回写改用独立 Governance Review。
- 根目录权威交互视觉基线：38/62 双栏，左侧团队群聊，右侧累计产物画布。
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
- D5 确定性定义链路底座：版本化 Project Brief、幂等澄清、精确 Context Pack、G0/G1 状态转移、AgentMembership、定义产物提交和 cursor SSE 基础。
- DeepSeek 异步 Adapter：SecretRef、认证错误脱敏、结构化输出、工具调用、SSE、超时、429 和上下文过长类型化；真实冒烟证据见 [Markdown](./evidence/d5-deepseek-smoke-2026-08-22.md) / [HTML](./evidence/d5-deepseek-smoke-2026-08-22.html)。
- D5 Agent Runtime：4 Agent 冻结注册、D5 角色激活边界、`model → policy → finish` 有界 LangGraph、`allow/ask/deny`、持久化 checkpoint、跨 Service 恢复、副作用对账与 cursor Event。脱敏台账见 [HTML](./evidence/d5-agent-runtime-progress-2026-08-22.html) / [JSON](./evidence/d5-runtime-smoke-2026-08-22.json)。
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

- D5 尚未完成；Factory Lead 产品项目已到 open G0 但未决定。隔离 fixture 的真实 Reviewer / Red Team Review / G1 open 已纵向运行，但不等于产品 G1 决定或来源质量人工审批。
- AI PM 最终 Run 使用 1 次博查、3 次有界模型尝试（2 次 schema retry）；Reviewer 使用 2 次尝试（1 次 schema retry）。失败正文未记录，仅保留状态、Hash、Token、Journal 和错误码。
- Codex CLI Adapter 完整 Builder 执行和真实受限项目工作区；当前只有 `--version` 只读 smoke。
- CopilotKit/AG-UI 流式事件；当前使用带 cursor 的短轮询降级。
- Gate/Permission 的原因、脱敏参数摘要等扩展字段与完整状态投影。
- 有效原生截图归档；本轮 ego-lite DOM/交互已检查，但 `Page.captureScreenshot` 超时。
- 真实 429 未观察；配置名 `deepseek-chat` 当前观察到服务端响应名 `deepseek-v4-flash`；Provider 返回 Token 但不返回 cost，Runtime 不伪造费用。
- 完整纵向联调、AG-UI 长连接、真实浏览器恢复和模型质量评审仍未完成。
- 登录、内网发布、PostgreSQL/Artifact 备份恢复和真实 URL。
- 第一个企业内部 dogfood 项目与效率/质量数据。

## 3.1 当前可重复验证的证据

- 2026-08-22 PostgreSQL `16.15` 在线，migration 已到 `20260822_0004 (head)`；本轮完成 `0003 → 0004 → 0003 → 0004` 往返。
- `pnpm test:api:integration`：42/42 通过；覆盖双击并发、重复提交、Permission 缺失拒绝、Reviewer 输入、Red Team Review 重放、G1 只开一次和 cursor 连续恢复。
- Factory Lead 真实对齐：两轮均 1 turn / 0 retry，共 6,633 Token；requested `deepseek-chat`、observed `deepseek-v4-flash`，完成后 `waiting_g0`。证据：[HTML](./evidence/d5-factory-lead-alignment-smoke-2026-08-22.html)。
- 博查 Adapter 与 Agent/Provider 定向测试 25/25；DeepSeek 真实冒烟 7 项通过、1 项未观察。隔离 AI PM / Reviewer / G1 open 脱敏证据：[JSON](./evidence/d5-ai-pm-research-smoke-2026-08-22.json) / [Runtime](./evidence/d5-agent-runtime-progress-2026-08-22.html)。
- 2026-08-22 使用真实浏览器检查更新后的 README、handoff、Runtime 和 Bocha 证据 HTML：`1440×900` / `390×844` 均无页面级横向溢出；该结果不替代产品 Web 视觉 QA。
- `pnpm check`：ESLint、TypeScript、Vitest 6/6、Ruff 和 Python 单测通过；PostgreSQL 集成测试默认显式跳过，须用上一命令单独运行。
- `pnpm build`：Next.js 16.3.1 production build 通过，`/`、`/projects/[projectId]`、`/settings` 和同源 API proxy 均生成。
- ego-lite：`1440×900` 保持 38/62 双栏，`390×844` 在同一屏切换群聊/产物，均无页面级滚动。`@Agent`、Gate 必填理由、React Flow 3 节点/2 边、MiniMap 3 节点、Artifact 安全内容和 Runtime 状态已跑通。原生截图捕获未通过，不能冒充为截图证据。
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

## 5. D3-D4 执行顺序

1. 读 `README.md`、`AGENTS.md`、本文、spec README/PRD/Technical Adaptation。
2. 完成 Spec Freeze Review，未通过不写应用代码。
3. 保存当前素材后初始化 Git，不删、不移动原始手册和 HTML。
4. 用 uv 创建 Python 3.12 环境；创建 Next.js/FastAPI monorepo 和 lockfile。
5. 配置 PostgreSQL 地址、Artifact/Workspace 根目录和本地安全边界。
6. 实现最小实体/API：Project、Message、Event、ContextVersion/Pack、Artifact/Version/Edge、Gate/Decision，以及 Task/Dependency、Run/Step、Permission 控制面。
7. 实现状态迁移、三态权限、任务原子认领、人工闸、幂等和副作用恢复单测。
8. 已将静态 mock 改为真实 API/Event/Gate/Permission 投影，并按根目录权威基线实现团队群聊 + Artifact 画布；模型未接入状态继续明确展示，不能伪装真模型。
9. 更新根 README/AGENTS 和 docs 中的真实命令、API、表、环境变量与完成状态。

## 6. 关键风险

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
