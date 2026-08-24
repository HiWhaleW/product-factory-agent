# 产品工厂 Agent - 项目级 Agent 指令

## 当前事实

- 日期：2026-08-24。
- 产品工厂 Agent 是 **AI Native 产品**：Agent 是主要执行者，不是普通后台上的聊天插件；自然语言、Context、Tool、Artifact、Gate、Reviewer 和反馈闭环共同构成产品核心。
- D1-D2 规格冻结包、独立工程排期、竞品/GitHub/标准 Harness 参考评估、4 份核心 Prompt 和 HTML 已生成。
- 四项 Spec Freeze 已于 2026-08-20 获用户明确批准；D1–D10 工程主线已推进到内部验收。
- Git/monorepo、FastAPI/Next.js、PostgreSQL 16.15、确定性控制面、真实用户/项目归属、用户模型凭据、Alembic `20260823_0010`、94 项通过且 48 项跳过的 Python 测试、48 项在线 PostgreSQL 集成/并发/恢复测试、Artifact 安全内容与单屏双栏 Web 已存在。
- 2026-08-24 最新核验：Web 34/34、Python 94/94（48 skipped）、PostgreSQL 48/48，production build、ESLint、TypeScript、Ruff 通过，Alembic 为 `20260823_0010 (head)`；内部 standalone 包 `20260824T074916Z` 的 SHA-256 manifest 在启动前后不变，4 份冻结 Prompt 哈希未变。项目软删除、用户隔离回收箱、幂等恢复、删除/恢复审计、API 空态、首次引导和精简个人信息已有真实 PostgreSQL 与历史两端浏览器 QA；新内部包尚未绑定或重新验收到用户环境，保留 1 条 Starlette/httpx 弃用警告。
- DeepSeek、博查 Adapter、有界 LangGraph Runtime、Run/Step/checkpoint 和 Codex Builder 真实执行已存在。销售复盘 Agent 已依次完成 G0–G5、后端开发、前端开发、MVP 与内部验收，当前为 `seed_beta / Context v10 / iteration v1`。
- 必须区分三个对象：“销售复盘 Agent”是产品工厂内的内部示范项目，其项目生命周期停在种子内测、G6 未打开；“产品工厂 Agent”是平台产品本身，下一步是 GitHub 更新和火山引擎部署；火山引擎 `user-beta` 是给真实用户测试平台的环境，不等于销售复盘 Agent 正式发布，也不需要先批准该示范项目的 G6。
- 用户已于 2026-08-23 批准销售复盘 Agent 的 G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a`；该示范项目的 G6 尚未打开。内部环境 `127.0.0.1:3200/8200` current / previous 为 `20260824T074916Z` / `20260824T042123Z`；独立用户环境 `127.0.0.1:3300/8300` current / previous 仍为 `20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`。用户环境尚未绑定或重新验收 `074916Z`；其数据库为 `20260823_0010`，项目、Artifact、Run、Gate、消息、用户模型凭据和内部项目均为 0。
- 可回收前端联合验收项目固定为 `c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001`；它是测试 fixture，不得冒充真实业务项目。
- 后续不会再分别启动 Agent Runtime、后端、前端三条并行任务线，也不存在后续“并线”步骤。当前工作区是唯一实现真相源；由同一个 coding task 按 Gate 串行完成 Runtime → API/数据库 → Web 投影 → 测试/浏览器 QA → 文档闭环。
- 2026-08-24 通过 GitHub Connector 只读核验：私有仓库 `HiWhaleW/product-factory-agent`，`codex/initial-import`，Draft PR #1 仍 open/draft，PR head 为 `69eb31d22430522f32c8db6b1151336756f42d01`。任何远端写入前必须再次用 Connector 核验真实 head。
- 用户已指定交接后的立即顺序：以已建立的内部可重现基线更新 GitHub Draft PR，再对火山引擎受控 `user-beta` 做账号、拓扑与费用预检。这是平台用户测试基础设施，可在销售复盘 Agent G6 之前建立；不得将其写成该示范项目的正式发布。本机独立用户环境仍保留历史组合包，未经新的绑定验收不得写成 `user_baseline_ready`，但它不阻塞 GitHub 后的云预检。
- 唯一权威交互视觉基线是根目录 `产品工厂Agent_Harness表.html`。`产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html` 只是把 12 阶段生命周期投影到该交互范式的修订版，不得反向覆盖视觉基线。
- 当前 Web 已移除 `demoProject`，在同一 Next.js 应用中统一 `/` 首页、`/projects` 真实项目列表、`/projects/{projectId}` 双栏工作区和 `/settings` API 设置页；顶部为“首页 / 项目列表 / 设置 / 个人信息”，无效“帮助”和虚假快捷键说明已移除。个人信息只显示名称、账号身份、登录状态和退出登录，不再默认展示用户 ID、运行模式、Session 原因或强制认证诊断。设置页只承载 API Key 的添加、替换和删除。真实项目支持受控软删除、用户隔离回收箱和恢复，不提供永久删除。
- 当前桌面工作区按用户最新确认稿采用约 `30/70` 双栏（左侧群聊、右侧产物画布）；根目录 Harness 的 `38/62` 是交互视觉基线的历史比例，不能反向覆盖用户最新确认。12 阶段仍为 `6×2`，移动 `390×844` 仍使用“群聊 / 产物”同屏切换。
- 用户已明确前端现有内容默认固定；本次首页、项目列表、设置页、个人信息、登录后返回首页及项目操作按钮修改已提前告知并获授权。设置页现可添加/替换/删除用户自己的 API Key，并配置 OpenAI-compatible HTTPS 接口和模型名；此前用户已确认历史组合包的内部浏览器验收通过，`design-qa.md` 最新状态记录内部可重现基线已就绪、本机用户旧包未绑定，不能把旧验收自动扩展到 `074916Z`。
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
2. **保持两套环境的受控版本边界。** 内部 current / previous 为 `20260824T074916Z` / `20260824T042123Z`，用户环境 current / previous 为 `20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`；后续更新仍必须先内部验收，用户环境不得反向作为内部开发数据源。
3. **使用已建立的内部可重现基线。** `20260824T074916Z` 已通过 standalone 打包、SHA-256 manifest 启动前后复核和冻结 Prompt 哈希复核；只上传可重现源码、构建配置、migration、测试与同步文档，不上传 `.runtime`、手工混合 `.next` 或不可重现发布产物。该结论不等于 `user_baseline_ready`。
4. **GitHub 只用 Connector。** 远端写入前重新核对 Draft PR head、扫描秘密与本机路径，使用 `force:false`，保持 Draft 且不 merge；不得使用 `gh` 或本地 push。
5. **预检并建立火山引擎 `user-beta`。** 先核验账号、地域、网络、资源、费用和拓扑；付费资源或目标不唯一时先请用户决定。云上新建独立 PostgreSQL、Artifact/Workspace、日志、Secret Store、Session Secret 和邀请哈希，完成 HTTPS、认证、SSE、隔离、恢复/回滚和浏览器验收。不得把带本地 Codex CLI/工作区能力的 Builder 直接暴露到公开 veFaaS 函数。
6. **保持本机用户环境的独立放行边界。** 它仍是历史组合包；如后续要绑定 `074916Z`，必须单独做 preflight、迁移和完整重验，不能把内部验收自动扩展过去。该动作不阻塞火山引擎预检。
7. **开展真实种子用户内测。** G5 已由用户批准；只收集真实任务、使用、失败和反馈数据，不得伪造内测证据。
8. **继续按对象管理 Gate。** 火山引擎 `user-beta` 部署不需销售复盘 Agent G6；销售复盘 Agent 若继续向正式发布推进，必须先用其真实内测证据生成 BRD、打开并由用户批准该项目 G6。
9. **跨层改动由同一任务负责闭环。** 修改 Runtime/API 时同步前端投影、测试、文档和浏览器 QA；不得留下“等待另一条线并入”的状态。

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

平台现有两套独立本机环境：内部验证环境 `3200/8200` current / previous 为 `20260824T074916Z` / `20260824T042123Z`；用户环境 `3300/8300` current / previous 为 `20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`。内部可重现 standalone 基线已经建立，manifest 启动前后不变，4 份冻结 Prompt 哈希未变；用户环境尚未绑定或重新验收该包。两端数据库、Artifact、Workspace、日志、Session Secret 和邀请码均独立；本机历史回滚边界已真实验收。下一步用 GitHub Connector 更新 Draft PR，再按 `docs/cloud-user-beta-handoff.md` 执行火山引擎账号、拓扑和费用预检。本机用户环境是否绑定新包是独立放行动作，不阻塞云预检。公网 HTTPS、云上验收和真实种子用户数据尚未完成。

1. 以内部 `20260824T074916Z` 可重现基线用 GitHub Connector 安全更新 Draft PR；随后按 `docs/cloud-user-beta-handoff.md` 执行火山引擎账号、拓扑和费用预检，再在用户确认精确资源边界后部署并验收 `user-beta`。
2. 使用真实种子用户和真实任务，按既定退出阈值收集成功、失败、使用和反馈数据。
3. 保留 Reviewer 的已知问题，并在真实内测中验证。
4. 销售复盘 Agent 若继续向其正式发布推进，内测证据达标后才生成商业 BRD 并打开该项目 G6；平台的火山引擎 `user-beta` 不以此为前置。
5. 前端非必要不动；确需修改必须提前告知用户。
6. AG-UI/SSE 和认证强制执行已完成；后续不得把 `2500ms` cursor 轮询重新降级为主通道。

## 交接提示词

使用 `docs/HANDOFF_PROMPT.md`。未得用户明确批准时，它只应该完成评审和报告，不应该开始写应用代码。

## 文档交付规则

- 后续新建或实质更新的、面向用户评审/阅读的 Markdown 交付物，必须在同目录同步提供同名 HTML 阅读版。
- Markdown 保留完整事实、契约和机器可读结构；HTML 负责 Web 端可视化阅读，不得删改关键结论、状态、风险或未验证项。
- HTML 默认自包含，不依赖外部 CDN；应提供清晰导航、响应式布局、可访问焦点态，并优先把架构、流程、对比和状态做成可视化结构。
- HTML 完成后必须尽可能做真实浏览器 QA，至少覆盖桌面 `1440x900` 和移动 `390x844`；未实际预览时必须明确标注未验证，不得声称可视化完成。
- `AGENTS.md`、Prompt、纯索引或机器指令文件本身无需机械生成 HTML，除非它们被作为用户阅读交付物输出。
