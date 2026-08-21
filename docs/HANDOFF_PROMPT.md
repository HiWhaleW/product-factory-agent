# 产品工厂 Agent - 交接提示词

> 适用：将本项目交给 Codex、Claude Code、Cursor 或其他可读写工作区的 coding agent。  
> 当前状态：四项 Spec Freeze 已批准，D3–D4 已收口，D5 尚未开始。

## 直接复制以下提示词

```text
你现在接手“产品工厂 Agent”项目。请把本次工作视为正式项目交接，先核验真实现状，再推进任务。

项目根目录：
<repo-root>

一、必须按顺序完整读取
先确认当前 Agent 已自动加载项目根目录 `AGENTS.md`；如当前客户端不会自动加载，则先手动读取它。然后严格按以下顺序：
1. README.md
2. docs/handoff.md
3. 产品工厂Agent/spec/README.md
4. docs/PRD.md
5. 产品工厂Agent/spec/Technical-Adaptation.md
6. 产品工厂Agent/spec/Engineering-Schedule.md
7. docs/materials-inventory.md

按任务再读：
- Agent 编排：Context-Schema.md、State-Machine-and-Gates.md、Capability-Registry.md、Tool-and-Permission-Policy.md、Harness-Reference-Assessment.md
- 前端/交互：Interaction-Spec.md、Frontend-Implementation-Spec.md
- 测试/放行：Acceptance-Test-Plan.md
- Agent Prompt：spec/prompts/ 相应文件
- 调研溯源：Competitor-and-OpenSource-Research.md、Agent-Prompt-Gap-Report.md、Harness-Reference-Assessment.md

不要一次把所有手册和规格塞入单个模型上下文，应按阶段加载。

二、必须先核验的事实
- D1-D2 规格、研究、4 份核心 Prompt 和 HTML 已完成文档收口，四项 Spec Freeze 已批准。
- 标准 Harness 参考只采用机制：双 DAG、Run Journal、三态权限、上下文压缩、后台回注和有界完成；不复制其 shell/线程/文件状态教学实现。
- Git/monorepo、FastAPI/Next.js、控制面模型/API、初始 Alembic migration 和真实双栏 Web 基础切片已存在。
- PostgreSQL 16.15、在线 migration、已实现 API 的数据库集成/并发幂等测试和 Web/API 基础投影已通过；LangGraph Run 图、DeepSeek、Codex Adapter 完整运行、部署和线上 URL 尚未完成。
- spec 中未被代码、migration 或真实运行证据覆盖的 API、数据表、路由、环境变量仍是目标契约。
- D3–D4 已收口。`pnpm check`、Next.js production build 与 `pnpm test:api:integration` 18/18 已通过；Web 6 项和 API 纯逻辑 19 项通过；普通 pytest 会显式跳过在线 PostgreSQL 组。
- 唯一权威交互视觉基线是根目录 `产品工厂Agent_Harness表.html`；子目录 Harness 文件只是 12 阶段生命周期适配投影，不得覆盖视觉基线。
- 当前 Web 已移除 `demoProject`，实现真实控制面投影、React Flow、Artifact 安全内容/下载和 Gate/Permission 独立卡片。ego-lite 已复验 `1440×900` 与 `390×844` 单屏工作区、`@Agent`、Gate 理由校验和 MiniMap 3 节点。原生截图通道超时，`design-qa.md` 保持 `blocked`，不得冒充为完整视觉 QA 通过。
- `docs/evidence/app-*.png`、`harness-mobile.png` 等只能作为历史快照，不能证明权威原型或 D3 应用交互符合性。
- 用户当前能提供的模型供应商是 DeepSeek；具体接入渠道、`MODEL_NAME`、`MODEL_BASE_URL`、工具调用和 Schema 兼容性最晚 D5 真模型切片前真实冒烟；D3-D4 可显式 mock。
- V1 不使用向量 RAG。Context Pack 按项目/阶段/产物/版本精确取回，不引入 embedding 模型或向量库。
- 项目使用有界 Agent Loop：模型→工具→结果可续跑，但受轮次、重试、超时、预算、Gate 和 Reviewer 限制。
- LangGraph 只负责 Agent Run 的循环、interrupt、checkpoint 和恢复；项目阶段、G0-G6、权限和幂等仍由确定性应用代码执行。LangGraph 不等于 RAG。
- 不得删除、移动或覆盖根目录三份手册、四份核心 HTML 和 spec/docs 产物。

三、核验 Spec Freeze 批准记录
以下四项已于 2026-08-20 获用户明确批准，不再重复询问：
1. V1 仅单用户/单管理员。
2. V1 仅 DeepSeek 一个模型供应商；接入渠道、模型名和 Base URL 最晚 D5 真模型切片前锁定并真实冒烟。
3. V1 Builder 使用本地 Codex CLI 适配器。
4. V1 优先本机/内网运行，不实现企业 SSO、多租户或云代码沙箱。

历史约束：批准前只能审查文档；当前已解除该开工限制。任何 G0-G6、工具 Permission 或外部发布权限仍必须按各自契约执行。

四、下一阶段 D5
D3-D4 收口证据见 `docs/evidence/d3-d4-closure-2026-08-21.md`。不要重复初始化或重写已收口控制面。

D5 只按真模型纵向切片推进：
a. 由用户提供 DeepSeek 接入渠道、模型名和 Base URL，API Key 只由本地安全环境变量/SecretRef 配置。
b. 在不暴露密钥的前提下完成认证、网络、流式、工具调用、JSON/Schema、中文长文档、超时/限流/Token/费用/context-too-long 冒烟。
c. 实现项目对齐、Project Brief/G0、AI PM 入群与最小 Context Pack。
d. 再实现 Evidence/MRD、Red Team Review、G1 与断线 cursor 续接。
e. 真模型冒烟未通过时 fail closed，不用 mock 放行 D5。

五、硬性实施约束
- 4 个核心 Agent：Factory Lead、AI PM、Builder、Reviewer。
- 12 个本轮用户阶段 + 下一轮迭代循环；开发内部固定后端→前端；G0-G6 = 七个必审闸。
- 双栏 UI：左侧项目群聊，右侧累计产物 DAG。
- 共享上下文使用版本化 Context Pack，不共享隐藏思维链、整段群聊或密钥原值。
- 用户可见 Artifact DAG 与内部 Execution Task DAG 分离；Context Pack 与 Run 上下文压缩分离。
- 状态转移、工具权限、预算、幂等和闸由确定性代码强制，不靠 Prompt 自律。
- 产品 Gate 与一次性 PermissionRequest 分离；Run 恢复外部副作用前必须按幂等键对账。
- 密钥只传 SecretRef，不进前端、仓库、群聊、DAG、Prompt、Context Pack 或日志。
- V1 不引入 17 个可见 Agent、SSO、多租户、多模型智能路由、云代码沙箱。
- V1 不将 Builder 运行在公开 veFaaS 函数环境。
- 开源复用分级：LangGraph/React Flow/CopilotKit/AG-UI 可作官方包依赖接入；LangGraph Agent Chat UI/OpenHands Agent Canvas 只做局部适配参考；`learn-claude-code-main`/MetaGPT/ChatDev/CrewAI 只迁移机制；E2B/ACP/OpenHands 后端延后 V2；GPT Pilot 禁止作依赖或代码来源。
- 任何“直接迁移”都不得整仓复制；必须核对 license，只集成最小模块，并通过本项目 Schema/权限/密钥/幂等/恢复测试。
- 未运行真模型不说 Agent 效果通过；未真浏览器 QA 不说前端完成。
- 页面能打开、构建通过、静态截图或无 Console 错误都不能证明权威交互符合性。
- 不删测试、隐藏错误、降低验收或用 mock 冒充真实验收。

六、每次完成后必须报告
- 实际修改文件。
- 运行的命令和测试证据。
- 仍未完成、未验证和被 mock 的部分。
- 任何与 spec 的偏离、原因、影响和回退条件。
- 需要用户批准的下一个闸。

现在请先完成上述必读和事实核验，然后给我：
1. 你理解的当前阶段和下一闸口；
2. 已完成 / 未完成的证据；
3. Spec Freeze 四项批准记录；
4. DeepSeek 接入仍缺的环境信息，但不要索要用户在群聊中粘贴 API Key；
5. 你发现的文档矛盾或风险。

继续 D3 范围内的安全实施；不要越过当前退出条件提前宣称 D3 完成或进入 D5。
```

## 用户批准后的继续短提示词

```text
我确认 Spec Freeze Review 的四项 V1 决策全部批准。

请先按 docs/HANDOFF_PROMPT.md 更新规格和交接状态为“已冻结”，然后只实现 D3-D4 工程骨架和最小状态/数据/API 基础。

不要提前实现 D5 的真实 AI PM/MRD 纵向切片。完成后运行自动测试，启动最小前后端骨架进行真实浏览器检查，同步 README/AGENTS/docs/handoff/operator-runbook/architecture。
```
