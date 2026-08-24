# 产品工厂 Agent - 素材全量索引

> 盘点日期：2026-08-24  
> 状态含义：`权威` = 后续开发的契约；`参考` = 提供默认和方法；`原型` = 用于交互理解，不是代码基础；`交接` = 当前阶段事实。
> HTML 阅读版：[materials-inventory.html](./materials-inventory.html)

## 1. 项目入口和交接

| 路径 | 受众 | 状态 | 用途 |
|---|---|---|---|
| [`README.md`](../README.md) | 人类/新 Agent | 交接 | 5 分钟项目入口和真实状态 |
| [`AGENTS.md`](../AGENTS.md) | Codex/开发 Agent | 权威 | 读取顺序、冻结边界、硬性约束和下一阶段 |
| [`CLAUDE.md`](../CLAUDE.md) | Claude Code | 路由 | 指向唯一权威 `AGENTS.md`，避免双份指令漂移 |
| [`docs/handoff.md`](./handoff.md) | 人类/接手者 | 交接 | 完成/未完成、决策、风险、开工顺序 |
| [`docs/handoff.html`](./handoff.html) | 人类评审 | 交接 | 交接状态、素材、架构、Prompt 和 Roadmap 可视化 |
| [`docs/HANDOFF_PROMPT.md`](./HANDOFF_PROMPT.md) | 下一位 Agent | 交接 | 可直接粘贴的交接提示词 |
| [`docs/HANDOFF_PROMPT.html`](./HANDOFF_PROMPT.html) | 人类评审 | 交接 | 当前种子内测、双环境、G6 边界与后续流程 |
| [`docs/environments.md`](./environments.md) / [HTML](./environments.html) | 开发/运维/接手者 | 权威交接 | 内部验证与独立用户环境的入口、数据边界、发布顺序和运维命令 |
| [`docs/cloud-user-beta-handoff.md`](./cloud-user-beta-handoff.md) / [HTML](./cloud-user-beta-handoff.html) | 开发/运维/接手者 | 交接 | 内部可重现基线、GitHub Connector 安全更新、火山引擎 `user-beta` 拓扑预检与云上验收；本机用户绑定为独立放行线 |
| [`docs/evidence/user-environment-acceptance-2026-08-23.md`](./evidence/user-environment-acceptance-2026-08-23.md) / [HTML](./evidence/user-environment-acceptance-2026-08-23.html) | 开发/评审 | 真实证据 | 用户与项目归属、独立数据库、空项目、安全、恢复和首版回滚保护 |
| [`docs/evidence/d3-d4-closure-2026-08-21.md`](./evidence/d3-d4-closure-2026-08-21.md) / [HTML](./evidence/d3-d4-closure-2026-08-21.html) | 开发/评审 | 工程证据 | D3–D4 退出命令、测试、ego-lite 交互和未完成边界 |
| [`design-qa.md`](../design-qa.md) / [HTML](../design-qa.html) | 设计/开发 | QA 证据 | 历史组合包的桌面/移动浏览器 QA 与最新内部可重现基线证据；当前状态为 `internal_reproducible_baseline_ready / cloud_preflight_pending / seed_beta`，本机用户绑定独立待执行 |
| [`docs/architecture.md`](./architecture.md) | 开发/架构 | 权威摘要 | 当前决策、系统边界、数据流和技术栈 |
| [`docs/operator-runbook.md`](./operator-runbook.md) | 开发/运维 | 交接 | 环境、开工前置、未来运行和故障边界 |
| [`docs/product-lifecycle.md`](./product-lifecycle.md) / [HTML](./product-lifecycle.html) | 全员 | 权威 | 12 阶段、后端→前端、G0-G6、D1-D10 与 B1-Bn 的唯一生命周期口径 |

## 2. D1-D2 权威规格

| 路径 | 状态 | 解决的问题 |
|---|---|---|
| [`产品工厂Agent/spec/README.md`](../产品工厂Agent/spec/README.md) | 权威 | 规格导航、冻结决策、10 日 Roadmap |
| [`docs/PRD.md`](./PRD.md) | 权威 | 产品定位、V1 范围、流程、Agent、人工闸和指标 |
| [`docs/PRD-Agent-Blueprint-Adaptation.md`](./PRD-Agent-Blueprint-Adaptation.md) | 已冻结补充规格 | `agent-blueprint` 参考裁决、7 层架构、贯穿数据流、真相源与分层验收；不替代现有 PRD |
| [`spec/Interaction-Spec.md`](../产品工厂Agent/spec/Interaction-Spec.md) | 权威 | 群聊、新 Agent 入群、`@Agent`、产物 DAG、预览、状态和 Design Tokens |
| [`spec/Frontend-Implementation-Spec.md`](../产品工厂Agent/spec/Frontend-Implementation-Spec.md) | 已冻结 | 三页面线框、组件树、Event 投影、全状态、响应式、DAG 规模策略和 D3-D8 前端任务 |
| [`spec/Context-Schema.md`](../产品工厂Agent/spec/Context-Schema.md) | 权威 | 五层上下文、Context Pack、Handoff、事实/假设/决定和脱敏 |
| [`spec/State-Machine-and-Gates.md`](../产品工厂Agent/spec/State-Machine-and-Gates.md) | 权威 | 项目状态、G0-G6、幂等、恢复和上线反馈路由 |
| [`spec/Capability-Registry.md`](../产品工厂Agent/spec/Capability-Registry.md) | 权威 | 4 个 Agent、12 个能力、原 17 岗位映射和动态 Agent 升格 |
| [`spec/Tool-and-Permission-Policy.md`](../产品工厂Agent/spec/Tool-and-Permission-Policy.md) | 权威 | 工具白名单、Codex CLI 工作区、风险、预算、Secret 和审计 |
| [`spec/Technical-Adaptation.md`](../产品工厂Agent/spec/Technical-Adaptation.md) | 已冻结权威规格 | 技术路线、DeepSeek 边界、无向量 RAG、有界 Agent Loop、开源复用分级；未被运行证据覆盖的 API/数据/部署仍是未来契约 |
| [`spec/Acceptance-Test-Plan.md`](../产品工厂Agent/spec/Acceptance-Test-Plan.md) | 权威 | 6 层放行、核心 E2E、真模型、浏览器、安全和 D10 判定 |
| [`spec/Engineering-Schedule.md`](../产品工厂Agent/spec/Engineering-Schedule.md) | 权威 | D1-D10 每日任务、关键路径、依赖、人工闸、缓冲、变更控制和完成定义 |

## 3. 调研和 Prompt

| 路径 | 状态 | 用途 |
|---|---|---|
| [`spec/Competitor-and-OpenSource-Research.md`](../产品工厂Agent/spec/Competitor-and-OpenSource-Research.md) | 参考 | Atoms、Replit Agent、Lovable、Bolt、v0 等竞品；LangGraph/React Flow/CopilotKit/AG-UI 等技术决策 |
| [`spec/Agent-Prompt-Gap-Report.md`](../产品工厂Agent/spec/Agent-Prompt-Gap-Report.md) | 权威报告 | V1 Prompt 覆盖和原 17 岗位缺口 |
| [`spec/Harness-Reference-Assessment.md`](../产品工厂Agent/spec/Harness-Reference-Assessment.md) | 权威报告 | `learn-claude-code-main` 新主线 s01-s17 机制裁决、反方测试和 D1-D2 规格增量 |
| [`spec/prompts/factory-lead.prompt.md`](../产品工厂Agent/spec/prompts/factory-lead.prompt.md) | v0.2 冻结 | 主 Agent 状态/路由/Context/闸/工具约束；已有真实运行证据 |
| [`spec/prompts/ai-pm.prompt.md`](../产品工厂Agent/spec/prompts/ai-pm.prompt.md) | v0.2 冻结 | MRD/PRD、种子内测分析、商业 BRD、范围与验收；已有真实运行证据 |
| [`spec/prompts/builder.prompt.md`](../产品工厂Agent/spec/prompts/builder.prompt.md) | v0.2 冻结 | 技术适配、纵向切片、Codex Adapter 和工程证据；已有真实运行证据 |
| [`spec/prompts/reviewer.prompt.md`](../产品工厂Agent/spec/prompts/reviewer.prompt.md) | v0.2 冻结 | 清洁上下文的文档/模型/工程/浏览器审核；已有真实运行证据 |

## 4. HTML 产物

| 路径 | 状态 | 用途 |
|---|---|---|
| [`产品工厂Agent_Harness表.html`](../产品工厂Agent_Harness表.html) | 权威交互视觉基线 | 历史基线为 38/62；当前用户确认稿覆盖为约 30/70，但仍保持团队群聊、成员/输入/Gate、产物节点/连线/缩放/预览/下载/URL 交互范式 |
| [`产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html`](../产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html) | 生命周期适配投影 | 将 12 阶段、G0-G6、后端→前端与内测后 BRD 投影到既有交互；不得替代根目录视觉基线 |
| [`产品工厂Agent/spec/index.html`](../产品工厂Agent/spec/index.html) | 权威可视化 | D1-D2 规格、Roadmap、通俗技术架构、RAG/Agent Loop/LangGraph 边界、开源复用、竞品、Prompt 和验收入口 |
| [`产品工厂Agent/spec/Harness-Reference-Assessment.html`](../产品工厂Agent/spec/Harness-Reference-Assessment.html) | 权威可视化 | 标准 Harness 机制、双 DAG、6 项规格增量和不可照搬实现 |
| [`产品工厂Agent/spec/Engineering-Schedule.html`](../产品工厂Agent/spec/Engineering-Schedule.html) | 权威可视化 | D1–D10 已完成工程主线、当前 G5 和 B1–Bn 后续流程 |
| [`docs/PRD-Agent-Blueprint-Adaptation.html`](./PRD-Agent-Blueprint-Adaptation.html) | 已冻结补充规格可视化 | `agent-blueprint` 适配 PRD 的 7 层架构、数据流、真相源、组件裁决和分层验收 |
| [`产品工厂Agent/spec/Frontend-Implementation-Spec.html`](../产品工厂Agent/spec/Frontend-Implementation-Spec.html) | 已冻结规格可视化 | 页面线框、组件树、事件/状态投影、前端排期和放行矩阵；不是已实现页面 |
| [`产品工厂Agent/spec/Technical-Adaptation.html`](../产品工厂Agent/spec/Technical-Adaptation.html) | 已冻结规格可视化 | 技术边界、真相源、分阶段环境值和开源复用分级；不是运行证据 |
| [`产品工厂Agent/spec/Acceptance-Test-Plan.html`](../产品工厂Agent/spec/Acceptance-Test-Plan.html) | 权威可视化 | 六层放行、D1-D2 清单、核心 E2E 和对抗测试 |
| [`docs/handoff.html`](./handoff.html) | 交接 | 阶段交接的可视化首页 |

## 5. 根目录原始工程手册

| 路径 | 状态 | 与本项目的关系 |
|---|---|---|
| [`AI产品Vibe Coding通用技术栈手册-技术选型spec.md`](../AI产品Vibe%20Coding通用技术栈手册-技术选型spec.md) | 参考 | 工程底线、技术适配、状态、双层测试、权限边界 |
| [`AI产品Vibe Coding通用前端技术栈手册.md`](../AI产品Vibe%20Coding通用前端技术栈手册.md) | 参考 | Agent 任务状态、空/失败/恢复、流式、前后端契约和真浏览器 QA |
| [`AI Agent 产品上线部署手册.md`](../AI%20Agent%20产品上线部署手册.md) | 参考 | 部署、密钥、数据、文件和监控底线；其 veFaaS/SQLite 默认被本项目 V1 偏离 |

## 6. 外部本地参考工程

| 路径 | 状态 | 采用边界 |
|---|---|---|
| `learn-claude-code-main`（本地参考资料） | 参考 | 只参考 Harness 机制和测试思路；不是产品依赖，不复制其 `shell=True`、字符串黑名单、终端审批、内存线程或文件状态实现 |
| `agent-blueprint`（本地参考资料） | 参考 | 仅吸收七层分层、可观测性与可靠性思路；适配裁决见 `docs/PRD-Agent-Blueprint-Adaptation.md/html`，不整仓复制 |

## 7. 当前实现与仍未完成

销售复盘 Agent 是内部示范项目，为 `seed_beta / Context v10 / iteration v1`；产品工厂 Agent 是平台产品；火山引擎 `user-beta` 是供真实用户测试平台的独立环境，不需销售复盘 Agent G6。最新验证：Web 34/34、Python 94/94（48 skipped）、PostgreSQL 48/48，production build、ESLint、TypeScript、Ruff 通过，Alembic `20260823_0010 (head)`；保留 1 条 Starlette/httpx 弃用警告。

真实群聊已包含 4 个 Agent 的入群记录和自我介绍；143 条执行记录已拆成 38 个消息间处理组。前端现有内容默认固定，后续如确需修改必须先告知用户。

当前有两套独立本机环境：内部验证 `3200/8200` current / previous 为 `20260824T074916Z` / `20260824T042123Z` 并保留销售复盘 Agent；用户环境 `3300/8300` current / previous 仍为 `20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`，采用独立数据库、文件与密钥，项目、Artifact、Run、Gate、消息和用户模型凭据均为 0。内部新包的 SHA-256 manifest 启动前后不变，4 份冻结 Prompt 哈希未变；用户环境尚未绑定或重验新包。AG-UI/SSE、认证强制执行、真实用户和项目归属已完成；登录成功统一打开首页；项目删除进入按用户隔离的回收箱，可幂等恢复到原阶段，V1 不提供永久删除。

仍未完成：

- 用已建立的内部 `20260824T074916Z` 可重现源码/构建基线，通过 GitHub Connector 更新 Draft PR；随后执行火山引擎账号、拓扑和费用预检。当前平台状态保持 `internal_reproducible_baseline_ready / cloud_preflight_pending`。
- 本机独立用户环境仍保留旧包；如需绑定同一基线，须单独重验且完成前不得标记本机 `user_baseline_ready`，但不阻塞云预检或用户确认后的云部署。
- 火山引擎 `user-beta` 的资源预检、部署、migration、健康、安全、隔离、备份/恢复、回滚和真实浏览器验收。
- 产品工厂平台的真实用户任务、使用和反馈数据。
- 销售复盘 Agent 若继续正式发布，其商业 BRD/G6、发布/交接和反馈迭代尚未完成；这不阻塞平台 `user-beta`。
- 公网域名/HTTPS 与云上真实跨版本回滚。
- DeepSeek 真实 429、博查费用/账单、来源质量人工评审和模型路由差异确认。
- GitHub 远端写入前仍须使用 Connector 重新核验 head；不得使用 `gh`、force push 或上传秘密/本机文件。
