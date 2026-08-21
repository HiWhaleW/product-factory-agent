# 产品工厂 Agent - 竞品与开源技术参考

> 调研日期：2026-08-20  
> 来源规则：优先产品官网、官方 GitHub 和官方 registry。  
> 限制：未对所有商业产品做登录后深度体验；交互和内部架构判断基于官方公开信息，需在 D3-D5 继续 dogfood 校验。

## 1. 结论

**市面上存在高度类似产品，不是空白市场。**

- 最接近的公开产品是 **Atoms（原 MGX/MetaGPT X）**：公开页面展示 Team Leader、Product Manager、Architect、Engineer、Researcher、Data Analyst、SEO/Ads 等 AI 员工，覆盖验证、规格、构建、测试、部署和增长，Team Leader 会请求用户批准。
- Replit Agent、Lovable、Bolt、v0 都是“自然语言想法 → 可运行/可部署应用”的直接替代。
- Devin 更靠近工程团队的长任务、多仓库、PR Review、视觉 QA、事故/工单处理和持续反馈闭环。
- 尚未从公开资料中找到同时强调以下组合的产品：**MRD/PRD 前置定义 + 种子内测后的商业 BRD + 可见团队群聊/@Agent + 累计业务产物 DAG + 确定性人工闸 + 反馈迭代分支**。这是产品工厂的当前差异化假设，不是已验证护城河。

## 2. 直接竞品

| 产品 | 官方公开定位/能力 | 与产品工厂重合 | 当前可见差异 | 官方来源 |
|---|---|---|---|---|
| Atoms（原 MGX） | AI Team 验证想法、建产品、测试、发布、获客；Team Leader 协调并请求批准 | 高：多角色产品团队、全周期、人工批准 | 产品工厂强调企业内部审计、产品文档证据闸和累计 DAG | [atoms.dev](https://atoms.dev/zh)、[MetaGPT](https://github.com/FoundationAgents/MetaGPT) |
| Replit Agent | 通过聊天从想法构建 production-ready app；自动 Web 搜索、集成 DB/Auth/第三方、浏览器测试与发布 | 高：非技术用户、聊天构建、测试、部署 | 更像强工程 Agent；公开页未强调 MRD/PRD 前置与内测后商业 BRD 的阶段证据闸 | [Replit Agent](https://replit.com/products/agent) |
| Lovable | 用自然语言构建、运行和管理完整产品/内部工具；预览、迭代、托管、认证、支付和集成 | 高：非技术用户、内部工具、端到端基础设施 | 产品工厂不包揽所有 Cloud，而是强调透明角色、证据、闸口和交接 | [Lovable](https://lovable.dev/) |
| Bolt | 聊天生成网站/应用/原型；自动模型路由、测试/重构、上下文管理、数据库/认证/托管 | 高：从想法到上线、产品经理/创业者用户 | 公开页强调一体化快速构建；未强调产品组织流程和证据审计 | [Bolt](https://bolt.new/) |
| v0 | Prompt → Build → Publish；GitHub 同步、Vercel 部署、Design Mode、设计系统；Agent 规划/创建任务/连数据库 | 高：全栈应用、可视化设计、发布 | 更强的 Web/Vercel 路径；产品工厂目标是企业内部可审计的产品交付链 | [v0](https://v0.app/) |

## 3. 间接竞品/替代方案

| 类别 | 代表 | 替代了什么 | 不完全重合原因 |
|---|---|---|---|
| AI 软件工程师 | Devin | 长任务、多仓库、PR/Visual QA、Issue/Incident、持续反馈与自动化 | 核心用户是工程团队，不是非技术产品负责人 | [Devin](https://devin.ai/) |
| 本地/自托管 Coding Agent | OpenHands Agent Canvas、Codex、Claude Code、Cursor | 代码读写、终端、测试、修复、仓库自动化 | 缺少完整产品定义和人工业务闸 |
| Agent/工作流平台 | Dify、Coze、n8n、CrewAI AMP、ChatDev 2.0 | 自定义 Agent/工作流、集成、运行与观测 | 用户必须编排工作流；产品工厂由主 Agent 管编排 |
| 项目/文档/协作 | Notion、Linear、Jira、Figma/FigJam | 需求文档、项目状态、评论和可视化 | 不会自主产出产品、代码和审核链 |
| 专家 Prompt/Skill 库 | 当前本地身份库、Codex Skills | 专业视角和方法 | 缺状态、上下文、工具权限和人工闸 |

## 4. 架构直接参考

| 项目 | 可参考 | 使用决策 | License / 风险 |
|---|---|---|---|
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | 一行需求→用户故事/竞品/需求/数据/API/文档；PM/架构/项目经理/工程师 + SOP | 参考角色契约和阶段产物，不直接作 V1 运行时 | MIT |
| [ChatDev](https://github.com/OpenBMB/ChatDev) | 1.0 虚拟软件公司的会议式协作；2.0 配置式多 Agent 平台与 DAG | 参考入群/会议/交接和 DAG，不直接复制 UI | Apache-2.0 |
| [OpenHands Agent Canvas](https://github.com/OpenHands/OpenHands) | 自托管 coding agent 控制中心；支持 OpenHands/Codex/Claude Code/Gemini/ACP 后端、Docker/VM/内部基础设施 | V1 参考 `CodingRuntimeAdapter`；V2 可评估直接接 ACP/OpenHands 后端 | MIT |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 持久执行、HITL、短/长期记忆、长任务和调试 | **V1 直接使用**作 Agent 图与 interrupt | MIT |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | 顺序/并行/交接/群组、checkpoint、streaming、HITL、time-travel、OpenTelemetry、YAML agents | 作 LangGraph 的备选与中长期评估；V1 不同时引入第二框架 | MIT |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | agents as tools/handoffs、guardrails、HITL、sessions、tracing、SandboxAgent | 参考 Prompt/工具/人工闸契约；V1 不与 LangGraph 重复 | MIT |
| [CrewAI](https://github.com/crewAIInc/crewAI) | Crews 角色自主 + Flows 确定性事件控制 | 参考“自主与精确流程分层”；不引入运行时 | MIT |

## 5. UI/协议/沙箱直接参考

> 这里的“直接使用”是安装官方开源包并按本项目 Schema/Adapter 集成，不是把任何整个示例仓库搬入代码库。整仓迁移会把不需要的产品假设、依赖和安全边界一起带入。

| 项目 | 官方能力 | V1 决策 |
|---|---|---|
| [React Flow](https://github.com/xyflow/xyflow) | React 节点 UI、边、缩放、Minimap、自定义节点 | **直接使用**实现产物 DAG |
| [CopilotKit](https://github.com/CopilotKit/CopilotKit) | 聊天、工具渲染、Generative UI、Shared State、HITL | **直接使用**作 Agent UI 层，但群聊/旁白使用自定义组件 |
| [AG-UI](https://github.com/ag-ui-protocol/ag-ui) | Agent-用户事件协议、SSE/WebSocket、双向状态、HITL | **直接使用**作后端-前端事件契约 |
| [assistant-ui](https://github.com/assistant-ui/assistant-ui) | 生产级聊天 primitives、流式、重试、附件、Markdown/代码、inline approvals | 作 UI/QA 参考；V1 不与 CopilotKit 双装 |
| [LangGraph Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) | Next.js + LangGraph 消息界面、事件显示/隐藏策略 | 参考连接和隐藏内部消息，不复制为单 Agent Chat |
| [tldraw](https://github.com/tldraw/tldraw) | 完整自由画布、协作、AI/工作流/分支聊天 starter | V1 不使用；仅在需自由绘制/注释时重评 |
| [E2B](https://github.com/e2b-dev/E2B) | 云端隔离代码沙箱、Python/JS SDK、可自托管 | V2 沙箱适配器；V1 因外部账号/费用/数据边界不引入 |

### 禁止参考

**GPT Pilot 不得作为代码依赖或克隆来源。**其官方 README 在 2026-08-20 检查时明确披露：2025-08-24 至 2026-06-11 期间仓库曾包含凭证窃取供应链恶意代码，项目不再维护。只能从概念层理解历史实现，不运行源码。

## 6. 差异化压力测试

| 假设 | 对抗性问题 | D3-D10 验证 |
|---|---|---|
| 群聊式团队更易理解 | 多 Agent 是否只增加表演性和 Token 成本？ | 用户能否正确找到责任 Agent；协调成本与修改次数 |
| MRD/PRD/方案/技术闸提高质量 | 是否只延缓了开发？ | 错误方向在写代码前的截停率 |
| 累计 DAG 比文件列表更有价值 | 25/100 节点后是否变成“意大利面”？ | 找到产物、影响分支和历史决定的时间 |
| 人工闸带来控制感 | 是否导致用户频繁被打断？ | G0-G6 的平均停留时间和退回质量 |
| 本地 Codex CLI 足够 | 是否存在工作区逃逸和本机泄密风险？ | 路径/软链接/密钥测试；决定是否提前引入沙箱 |
