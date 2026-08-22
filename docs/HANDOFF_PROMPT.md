# 产品工厂 Agent - 正式项目交接提示词

> 交接日期：2026-08-22  
> 适用范围：下一位负责项目安全入库、Agent Runtime/后端/前端并线和后续 Gate 推进的 coding agent  
> 当前状态：D5 定义链路进行中；“销售复盘 Agent”已由用户批准 G0/G1，当前为 `prd / Context v3`；用户已确认当前前端没有问题，Builder 尚未启动。

## 可直接复制的提示词

```text
你现在接手“产品工厂 Agent”正式项目交接与后续开发线。

项目根目录：
<项目根目录>

这是正式工作交接。前端、后端和 Agent Runtime 正在并线；不得重新初始化项目、覆盖用户或其他任务线修改、回退到 mock、擅自修改冻结规格或代替用户审批 Gate。

一、开始前必须完整读取和核验

1. 完整读取根目录 AGENTS.md。
2. 严格按 AGENTS.md 顺序完整读取：
   - README.md
   - docs/handoff.md
   - 产品工厂Agent/spec/README.md
   - docs/PRD.md
   - 产品工厂Agent/spec/Technical-Adaptation.md
3. 按工作线继续读取：
   - Agent 编排：Context-Schema、State-Machine-and-Gates、Capability-Registry、Tool-and-Permission-Policy、Harness-Reference-Assessment。
   - 前端：Interaction-Spec、Frontend-Implementation-Spec、Acceptance-Test-Plan、design-qa.md。
   - 工程实施：Engineering-Schedule。
   - 对应 Agent：spec/prompts/ 中对应 Prompt。
4. 检查 git status、remote、真实代码、migration/API/Event 投影、PostgreSQL/服务状态和现有浏览器状态，保留所有现有修改。
5. 浏览器只能使用 ego-lite / ego-browser，不得使用 Chrome、Playwright 或其他浏览器工具。

二、当前真实状态

- `/`、`/projects/{projectId}`、`/settings` 属于同一个 Next.js 应用；曾验证的生产入口为 http://127.0.0.1:3100/，接手时必须重新核验。
- Web 已接真实 FastAPI/PostgreSQL，不是 demoProject 或静态 mock。当前旧项目中的消息和样例 Artifact 仍可能是人工/控制面验证数据，不能冒充 Runtime Agent 生成。
- “销售复盘 Agent”已完成 Brief v1、用户批准 G0、Evidence Index/MRD v2、Red Team Review v2、用户批准 G1，当前为 `prd / Context v3`。两项已知问题必须保留：引用粒度待用户访谈验证；Gong 定价和客户规模缺少直接证据。
- 当前 Web 同源 API 尚需恢复/暴露该真实项目；不得用“D3 双栏交互验收”代替 D5 业务验收。
- 用户已确认当前前端没有问题。桌面为最新约 30/70 双栏，12 阶段 6×2，移动 390×844 使用“群聊 / 产物”切换。底层 2500ms cursor 短轮询仍是 AG-UI/SSE 未完成前的降级方案；可见提示标签已删除。
- 当前本地 main 是无提交分支，安全项目文件均为 untracked；仅确认 origin 指向 https://github.com/HiWhaleW/product-factory-agent.git。旧文档中的 codex/initial-import 和 Draft PR #1 未在本轮通过 GitHub 插件核验，不能当作已确认事实。
- Builder、MVP、种子内测、商业 BRD/G6、发布和线上地址仍未完成。

三、接手后必须完成的第一件事：使用 GitHub 插件安全推送

1. 只能使用 GitHub 插件/Connector 完成远端读取、建/更新分支、上传/提交文件和 PR 更新；不得使用 gh CLI。
2. 先用插件核验仓库默认分支、codex/initial-import、Draft PR #1 的真实状态，再决定创建或更新非破坏性分支/PR。
3. 不得 force push、重建仓库、覆盖远端其他任务线或未经审查整包提交全部 untracked 文件。
4. 推送前执行秘密与本机路径检查，严格遵循 .gitignore。不得上传 .env、.runtime、.venv、node_modules、.next、Artifact/Workspace、缓存、SecretRef 原值、本机来源路径和敏感 QA 文件。
5. GitHub 插件未安装、不可调用或无写权限时，停止远端写入并请求安装/授权；不得回退到 gh。
6. 完成后记录 repo、分支、commit/PR 链接、插件证据、上传清单和排除清单。

四、接手后必须完成的第二件事：向 Agent Runtime / 后端同步

1. 将“销售复盘 Agent”恢复/暴露到 Web 当前使用的同一 PostgreSQL/API，并保证前端能读取 Evidence Index v2、MRD v2、Red Team Review v2 和真实 G1 卡。
2. G1 返回结构化 known_issues[]，至少包含 issue、severity、evidence_refs/source_refs、status；不得让前端从正文猜字段。
3. 补 Artifact 真实版本索引：version、status、created_at、created_by/agent、content availability；latest v2 必须能核验真实历史版本。
4. 提供真实 agent.joined、Run、Task、Tool、streaming/recovery/cursor 事件和可回收 PermissionRequest/Gate 验收样本。
5. 对齐 Project iteration_version、Graph owner/agent、created_at，以及登录/Session、/me、logout、过期原因契约。
6. 明确 2500ms cursor 轮询只是降级；AG-UI/SSE 完成前不得宣称实时 transport 已完成。

五、接手后必须完成的第三件事：按 Gate 推进后续安排

1. 先完成 GitHub 安全快照和远端事实核验。
2. Runtime/后端统一销售复盘项目真相源；前端验收真实 Evidence/MRD/Red Team v2、G1 两项 known issues 和版本索引。
3. 完成 AI PM PRD Run、确定性 PRD 持久化和 G2 契约；G2 必须等待用户决定。
4. G2 后推进方案/G3、技术栈/G4；G4 前不得启动 Builder。
5. G4 后固定按后端开发 → 前端开发推进，双方分别提供 Execution Task、AgentRun、RunStep、测试和 ArtifactVersion 证据。
6. 再进入 MVP、内部验收/G5、种子内测、商业 BRD/G6、发布/交接和反馈迭代。
7. Builder、MVP、内测或发布没有真实证据前不得宣布完成。

六、前端冻结边界与验收

- 唯一权威交互视觉基线是根目录 产品工厂Agent_Harness表.html；用户最新明确标注优先于基线中的历史视觉比例，但不授权重做交互流程。
- 保持左群聊/右产物 DAG、12 阶段 6×2、移动切换、页面级不滚动、Artifact 拖动仅改本地视图、抽象 MiniMap，以及现有 Gate/Permission/预览/参与者/输入逻辑。
- 不修改 4 个 Agent、12 阶段、G0-G6、技术栈和业务状态契约。
- 前端改动只限 apps/web/**、前端资产和 QA 证据；API 字段不足时记录需求，不伪造字段、不直接修改后端。
- 每轮前端修改后用 ego-lite 在生产模式验证 1440×900 和 390×844，运行 pnpm lint:web、pnpm typecheck、pnpm test:web、pnpm build，并同步 design-qa.md/html 和 docs/evidence。
- 不可逆 Gate 只能用专用可回收验收项目；没有安全样本时记录未测，不得代批。

七、最终汇报必须包含

- GitHub 插件核验与安全推送结果；repo、分支、commit/PR 链接及排除项。
- 已向 Runtime/后端同步的字段清单、回应和仍未解决的契约缺口。
- 当前项目阶段、下一 Gate、后续执行顺序和明确禁止越过的边界。
- 实际代码/文档修改、测试和 ego-lite 证据。
- 尚未完成、未安全测试或需要用户决定的事项。

没有插件证据不得声称 GitHub 已同步；没有真实模型/数据库/浏览器证据，不得借其他任务线证据宣布对应能力完成。
```

## 交接边界摘要

- 本交接从“前端视觉线”升级为项目级正式交接。
- 下一位首先负责 GitHub 插件安全入库，再负责 Runtime/后端真相源对齐，最后按 G2→G6 顺序推进。
- 前端当前确认稿已通过，不是静态原型；后续如有修改仍只做增量并保留真实 API 投影。
- 人工 Gate、秘密、真实证据和并线修改是不可越过的边界。
