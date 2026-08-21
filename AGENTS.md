# 产品工厂 Agent - 项目级 Agent 指令

## 当前事实

- 日期：2026-08-22。
- D1-D2 规格冻结包、独立工程排期、竞品/GitHub/标准 Harness 参考评估、4 份核心 Prompt 和 HTML 已生成。
- 四项 Spec Freeze 已于 2026-08-20 获用户明确批准；D3–D4 已于 2026-08-21 收口，D5 正在进行。
- Git/monorepo、FastAPI/Next.js、PostgreSQL 16.15、D5 确定性控制面、Alembic `20260822_0004`、42 项在线集成/并发/恢复测试、Artifact 安全内容与单屏双栏 Web 已存在。
- DeepSeek、博查 Adapter、有界 LangGraph Runtime 和 Run/Step/checkpoint 已存在。真实 Factory Lead 产品项目已完成“模糊输入 → 3 个澄清 → Brief v1 → 打开 G0”，保持 `alignment` 且 G0 未代批。隔离 fixture 已真实贯通“博查 → AI PM → Evidence/MRD 确定性落库 → Reviewer → Red Team Review → 打开 G1”；G1 未代批且 fixture 项目保持 `mrd`。Codex Builder 完整执行、部署和线上地址仍不存在。
- 唯一权威交互视觉基线是根目录 `产品工厂Agent_Harness表.html`。`产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html` 只是把 12 阶段生命周期投影到该交互范式的修订版，不得反向覆盖视觉基线。
- 当前 Web 已移除 `demoProject`，接入真实项目创建/列表、群聊输入、参与者、Event cursor、Gate/Permission 和 React Flow Artifact DAG；ego-lite 已检查桌面/移动 DOM 与交互，但原生截图归档仍阻塞，不能宣称权威视觉完整验收通过。
- `docs/evidence/app-*.png`、`harness-mobile.png` 是历史 mock/原型快照；只能证明对应页面当时可见，不能证明权威交互符合性。权威原型和 D3 应用均尚无本轮可复现的完整浏览器符合性验收。
- DeepSeek 渠道、模型名、Base URL 和本地 SecretRef 已配置并真实冒烟；配置名 `deepseek-chat` 与流式返回元数据 `deepseek-v4-flash` 的差异待确认，不得据此虚报完整 Agent 效果通过。
- `产品工厂Agent/spec/Technical-Adaptation.md` 中未被代码、migration 或真实运行证据覆盖的 API/数据库/环境变量仍是未来契约，不是已实现事实。

## 必读顺序

1. `README.md`
2. `docs/handoff.md`
3. `产品工厂Agent/spec/README.md`
4. `docs/PRD.md`
5. `产品工厂Agent/spec/Technical-Adaptation.md`

然后按当前任务加载：

- Agent 编排：Context、State/Gates、Capability、Tool Policy、Harness Reference Assessment。
- 前端：Interaction Spec + Frontend Implementation Spec。
- 工程实施：Engineering Schedule。
- 放行/验收：Acceptance Test Plan。
- Prompt：`spec/prompts/` 中对应文件。

不要在一次模型上下文中加载所有手册和规格。

## 已批准的 V1 产品边界

- 4 个核心 Agent：Factory Lead、AI PM、Builder、Reviewer。
- 12 个本轮用户可见阶段：项目对齐、MRD、PRD、方案确认、技术栈确认、分阶段开发、MVP、内部验收、种子用户内测、BRD/商业模式确认、发布/交接、数据与反馈；之后进入下一轮迭代。
- 分阶段开发内部固定为后端开发 → 前端开发，均需独立 Task/Run/测试证据。
- G0-G6：7 个必审闸；全局规则回写使用独立 Governance Review。
- 双栏工作区：左侧项目群聊，右侧累计产物 DAG。
- 共享上下文使用版本化 Context Pack，不共享隐藏思维链、整段群聊或密钥原值。
- 用户可见 Artifact DAG 与内部 Execution Task DAG 分离；Context Pack 与 Run 上下文压缩分离。
- V1 单用户/单管理员、DeepSeek 单模型供应商、本机/内网、本地 Codex CLI 适配器。
- V1 不做企业 SSO、多租户、多模型智能路由、云代码沙箱或 17 个可见 Agent。

## 硬性约束

- 状态转移、工具权限、预算、幂等和人工闸由确定性代码执行，不依赖 Prompt 自律。
- Tool 权限必须输出 allow/ask/deny；产品 Gate 与一次性 PermissionRequest 不得混用。
- Agent Run 必须有可恢复 Journal/Step；恢复外部副作用前先按幂等键对账。
- 未经对应的 G0-G6 不得越过项目对齐、MRD、PRD、方案、技术栈、内部验收和商业发布决定。
- 未运行真实模型不得声称 Agent 效果通过。
- 未真实浏览器预览不得声称前端完成。
- 不用 mock、删测试、隐藏错误或降低验收来宣布完成。
- 密钥不进前端、仓库、群聊、Context Pack、DAG、日志或产物；只传 SecretRef。
- Builder 只能读写已批准项目工作区；V1 禁止自动 push/deploy/工作区删除。
- 反馈创建新分支，不改写已上线历史。

## 冻结技术路线

- Next.js 16.3.1 / React 19.2.8 / Tailwind 4.3.3。
- React Flow 12.11.3 作产物 DAG。
- CopilotKit 1.68.1 + AG-UI 0.0.58 作 Agent UI/事件契约。
- FastAPI 0.141.1 / Pydantic 2.13.4 / LangGraph 1.2.11。
- PostgreSQL 16.x / SQLAlchemy 2.0.52 / Alembic 1.19.1。
- Codex CLI Adapter；当前本机检测版本 `0.148.0-alpha.15`，路径通过 `CODEX_CLI_PATH` 配置，不在代码硬编码。

## 下一阶段任务

D3-D4 已收口，D5 正在进行。真实 Factory Lead 产品项目仍在 `waiting_g0`；隔离 AI PM→Reviewer→G1 纵向链路和确定性契约已通过。下一步是用户决定真实产品 G0；批准后才能在真实产品上运行 AI PM/Reviewer，并最终等待用户 G1。真实 429、博查费用/账单、来源质量人工评审和模型路由差异保持未验证。

1. 用户决定真实产品 G0；Agent、Prompt、PermissionRequest 和隔离 fixture 不得代批。
2. G0 批准后，Agent Runtime 使用稳定 `DefinitionSubmissionCreate` 提交 AI PM 提案；不得直接写业务表。
3. Reviewer 只消费 `definition-review/v1` 的已批准普通事实与独立只读 review candidates，并用 `DefinitionReviewCreate` 提交结果。
4. G1 必须等待用户人工决定；不得由 Agent 或测试 fixture 代批。
5. Builder 保持 D5 禁用，不宣称代码开发、MVP、内测或发布完成。

## 交接提示词

使用 `docs/HANDOFF_PROMPT.md`。未得用户明确批准时，它只应该完成评审和报告，不应该开始写应用代码。

## 文档交付规则

- 后续新建或实质更新的、面向用户评审/阅读的 Markdown 交付物，必须在同目录同步提供同名 HTML 阅读版。
- Markdown 保留完整事实、契约和机器可读结构；HTML 负责 Web 端可视化阅读，不得删改关键结论、状态、风险或未验证项。
- HTML 默认自包含，不依赖外部 CDN；应提供清晰导航、响应式布局、可访问焦点态，并优先把架构、流程、对比和状态做成可视化结构。
- HTML 完成后必须尽可能做真实浏览器 QA，至少覆盖桌面 `1440x900` 和移动 `390x844`；未实际预览时必须明确标注未验证，不得声称可视化完成。
- `AGENTS.md`、Prompt、纯索引或机器指令文件本身无需机械生成 HTML，除非它们被作为用户阅读交付物输出。
