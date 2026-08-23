# 产品工厂 Agent - 项目级 Agent 指令

## 当前事实

- 日期：2026-08-23。
- 产品工厂 Agent 是 **AI Native 产品**：Agent 是主要执行者，不是普通后台上的聊天插件；自然语言、Context、Tool、Artifact、Gate、Reviewer 和反馈闭环共同构成产品核心。
- D1-D2 规格冻结包、独立工程排期、竞品/GitHub/标准 Harness 参考评估、4 份核心 Prompt 和 HTML 已生成。
- 四项 Spec Freeze 已于 2026-08-20 获用户明确批准；D1–D10 工程主线已推进到内部验收。
- Git/monorepo、FastAPI/Next.js、PostgreSQL 16.15、确定性控制面、真实用户/项目归属、用户模型凭据、Alembic `20260823_0010`、86 项 Python 测试、48 项在线 PostgreSQL 集成/并发/恢复测试、Artifact 安全内容与单屏双栏 Web 已存在。
- 2026-08-23 最新核验：Web 26/26、Python 86/86、PostgreSQL 48/48、production build 通过，Alembic 为 `20260823_0010 (head)`。项目软删除、用户隔离回收箱、幂等恢复、删除/恢复审计和 API Key 表单校验已通过真实 PostgreSQL 与浏览器 QA；保留 1 条 Starlette/httpx 弃用警告。
- DeepSeek、博查 Adapter、有界 LangGraph Runtime、Run/Step/checkpoint 和 Codex Builder 真实执行已存在。销售复盘 Agent 已依次完成 G0–G5、后端开发、前端开发、MVP 与内部验收，当前为 `seed_beta / Context v10 / iteration v1`。
- 用户已于 2026-08-23 批准 G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a`，并于 2026-08-24 明确确认本次内部浏览器验收通过。内部验证环境 `127.0.0.1:3200/8200` 保留销售复盘 Agent；独立用户环境 `127.0.0.1:3300/8300` 使用独立数据库且首次登录为空项目。两套环境现均绑定已验收发布包 `20260823T155102Z`；用户数据库已迁移到 `20260823_0010`，Secret Store、备份恢复和 `095514Z ↔ 155102Z` 双向回滚演练通过，最终恢复到新包。G6 尚未打开，不得正式发布。
- 可回收前端联合验收项目固定为 `c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001`；它是测试 fixture，不得冒充真实业务项目。
- 后续不会再分别启动 Agent Runtime、后端、前端三条并行任务线，也不存在后续“并线”步骤。当前工作区是唯一实现真相源；由同一个 coding task 按 Gate 串行完成 Runtime → API/数据库 → Web 投影 → 测试/浏览器 QA → 文档闭环。
- GitHub Connector 本地可核验的最后安全快照是 `db39b5dd…` / Draft PR #1。任务表中无证据的 `4cac2589…` 已删除；下一位在任何远端写入前必须用 GitHub Connector 重新核验真实 head。
- 唯一权威交互视觉基线是根目录 `产品工厂Agent_Harness表.html`。`产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html` 只是把 12 阶段生命周期投影到该交互范式的修订版，不得反向覆盖视觉基线。
- 当前 Web 已移除 `demoProject`，在同一 Next.js 应用中统一 `/` 首页、`/projects` 真实项目列表、`/projects/{projectId}` 双栏工作区和 `/settings` API 设置页；顶部为“首页 / 项目列表 / 设置 / 个人信息”，无效“帮助”和虚假快捷键说明已移除。个人信息承载用户与 Session 内容；设置页只承载 API Key 的添加、替换和删除。真实项目支持受控软删除、用户隔离回收箱和恢复，不提供永久删除。
- 当前桌面工作区按用户最新确认稿采用约 `30/70` 双栏（左侧群聊、右侧产物画布）；根目录 Harness 的 `38/62` 是交互视觉基线的历史比例，不能反向覆盖用户最新确认。12 阶段仍为 `6×2`，移动 `390×844` 仍使用“群聊 / 产物”同屏切换。
- 用户已明确前端现有内容默认固定；本次首页、项目列表、设置页、个人信息、登录后返回首页及项目操作按钮修改已提前告知并获授权。设置页现可添加/替换/删除用户自己的 API Key，并配置 OpenAI-compatible HTTPS 接口和模型名；用户已确认本次内部浏览器验收通过，`design-qa.md` 状态为 `user_accepted / user_environment_ready`。
- AG-UI/SSE 已成为事件主通道：持久化事件使用 AG-UI CUSTOM envelope，SSE `id` 绑定数据库 sequence，支持 cursor/`Last-Event-ID`、心跳、断线降级和自动重连；`2500ms` cursor 轮询只在断线时启用，恢复后停止。
- 认证强制执行已完成：生产环境必须开启认证并配置邀请哈希/Session Secret；受保护 API 使用 HttpOnly Session，缺失、无效或过期均 fail closed。真实 `.env` 未被本轮修改。
- 用户 API Key 原文只保存在分环境、分用户、权限为 `0600` 的 Secret Store；PostgreSQL 保存 SecretRef、SHA-256 指纹、脱敏尾号及非敏感的接口名称/Base URL/模型名，API/校验错误不返回 Key 原文。Runtime 优先按项目 owner 使用用户配置的 OpenAI-compatible HTTPS 接口；普通用户未配置时 fail closed；`DEEPSEEK_API_KEY` 只允许内部管理员本地测试回退。
- Factory Lead 现有能力可以澄清输入，并受 `maxTurns/maxRetries/timeout/tool budget` 限制，但尚无确定性 feasibility/preflight 分类器；不得声称它能可靠识别所有“绝对不可能目标”或在模型调用前自动省下 Token。
- `docs/evidence/app-*.png`、`harness-mobile.png` 仍是历史 mock/原型快照；最新前端证据以 `design-qa.md` 和 `docs/evidence/d5-*-production-*-2026-08-22.png` 为准。
- DeepSeek 渠道、模型名、Base URL 和本地 SecretRef 已配置并真实冒烟；配置名 `deepseek-chat` 与流式返回元数据 `deepseek-v4-flash` 的差异待确认，不得据此虚报完整 Agent 效果通过。
- `产品工厂Agent/spec/Technical-Adaptation.md` 中未被代码、migration 或真实运行证据覆盖的 API/数据库/环境变量仍是未来契约，不是已实现事实。

## 必读顺序

1. `README.md`
2. `docs/handoff.md`
3. `docs/environments.md`
4. `产品工厂Agent/spec/README.md`
5. `docs/PRD.md`
6. `产品工厂Agent/spec/Technical-Adaptation.md`

然后按当前任务加载：

- Agent 编排：Context、State/Gates、Capability、Tool Policy、Harness Reference Assessment。
- 前端：Interaction Spec + Frontend Implementation Spec。
- 工程实施：Engineering Schedule。
- 放行/验收：Acceptance Test Plan。
- Prompt：`spec/prompts/` 中对应文件。

不要在一次模型上下文中加载所有手册和规格。

## 当前接手与执行规则

完成上述阅读和真实状态核验后，下一位接手者必须按顺序执行：

1. **把当前工作区作为唯一真相源。** 不再创建 Runtime、后端或前端并行任务，不等待后续并线；不覆盖现有实现，也不把某一层的局部通过当作端到端完成。
2. **使用已验收的用户环境开展测试。** 内部和用户环境现均为 `20260823T155102Z`；用户环境迁移、Secret Store、恢复和跨版本回滚已验收。不得把用户环境反向作为内部开发数据源。
3. **开展真实种子用户内测。** G5 已由用户批准；只收集真实任务、使用、失败和反馈数据，不得伪造内测证据。
4. **继续按 Gate 串行推进。** 真实内测证据达标后再做 BRD 并打开 G6；G6 批准后才发布/交接。
5. **跨层改动由同一任务负责闭环。** 修改 Runtime/API 时同步前端投影、测试、文档和浏览器 QA；不得留下“等待另一条线并入”的状态。
6. **GitHub 仍只用 Connector。** 现有安全快照和 Draft PR 已建立；后续推送前重新核对远端 head、扫描秘密与本机路径，并继续使用 `force:false`，不得使用 `gh`。

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

- 不得把产品降级为“传统 CRUD 工作流 + AI 聊天框”。每个核心闭环都应体现 Agent 感知上下文、受控行动、产生可追溯产物、接受独立审查、恢复执行和基于反馈迭代。
- 确定性控制面不是削弱 AI Native，而是为 Agent 的自主行动提供可信边界；业务状态和权限仍不能交给模型自由决定。
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
- Codex CLI Adapter 路径通过 `CODEX_CLI_PATH` 配置，不在代码硬编码；Builder 已有真实执行证据，但 V1 仍禁止自动 push/deploy/删除工作区。

## 下一阶段任务

销售复盘 Agent 当前为 `seed_beta / Context v10 / iteration v1`。G0–G5、后端、前端、MVP、内部验收、Beta Candidate 和本机内测环境验收已完成；真实 429、博查费用/账单、来源质量人工评审和模型路由差异保持未验证。

平台现有两套独立本机环境：内部验证环境 `3200/8200` 与用户环境 `3300/8300`。用户环境的数据库、Artifact、Workspace、日志、Session Secret 和邀请码均独立；用户环境已有 current `20260823T155102Z` 与 previous `20260823T095514Z`，双向回滚已真实演练并最终恢复到新包。公网域名、HTTPS 和真实种子用户数据尚未完成。

1. 使用真实种子用户和真实任务，按既定退出阈值收集成功、失败、使用和反馈数据。
2. 保留 Reviewer 的已知问题，并在真实内测中验证。
3. 内测证据达标后才生成商业 BRD 并打开 G6；G6 未批准前不得正式发布。
4. 前端非必要不动；确需修改必须提前告知用户。
5. AG-UI/SSE 和认证强制执行已完成；后续不得把 `2500ms` cursor 轮询重新降级为主通道。

## 交接提示词

使用 `docs/HANDOFF_PROMPT.md`。未得用户明确批准时，它只应该完成评审和报告，不应该开始写应用代码。

## 文档交付规则

- 后续新建或实质更新的、面向用户评审/阅读的 Markdown 交付物，必须在同目录同步提供同名 HTML 阅读版。
- Markdown 保留完整事实、契约和机器可读结构；HTML 负责 Web 端可视化阅读，不得删改关键结论、状态、风险或未验证项。
- HTML 默认自包含，不依赖外部 CDN；应提供清晰导航、响应式布局、可访问焦点态，并优先把架构、流程、对比和状态做成可视化结构。
- HTML 完成后必须尽可能做真实浏览器 QA，至少覆盖桌面 `1440x900` 和移动 `390x844`；未实际预览时必须明确标注未验证，不得声称可视化完成。
- `AGENTS.md`、Prompt、纯索引或机器指令文件本身无需机械生成 HTML，除非它们被作为用户阅读交付物输出。
