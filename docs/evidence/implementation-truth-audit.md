# 产品工厂 Agent - 当前事实审计

> 审计日期：2026-08-20  
> 当前阶段：D3 进行中，尚未满足 D3 退出条件  
> 原则：文件存在、依赖安装、构建通过、mock 可见、真实集成和产品验收是不同证据层级

## 1. 交互权威源

- 唯一权威交互视觉基线：`产品工厂Agent_Harness表.html`。
- 生命周期适配投影：`产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html`。它只同步 12 阶段、G0-G6、后端→前端和内测后商业 BRD，不得改变原交互范式。
- 冻结交互范式：桌面 38/62 双栏；左侧团队群聊、参与者、输入、Gate/Permission；右侧累计 Artifact DAG、节点/连线、缩放、预览、下载和 URL。

## 2. 当前工程事实矩阵

| 对象 | 真实存在 | 尚未证明/不存在 | 证据 |
|---|---|---|---|
| Git | `.git` 已初始化，分支 `main` | 没有任何 commit；当前文件均未被首个基线提交追踪 | `git status --short`、`git log` 报告 main 无提交 |
| Web | Next.js 3 个页面壳、12 阶段栏、静态事件卡、禁用 Gate 卡、线性节点 | 没有真实群聊输入/完整参与者区/预览抽屉；未使用 React Flow；未连接 API/SSE | `apps/web/app/**`、`apps/web/lib/demo-data.ts` |
| API | FastAPI 路由定义：Project、Message、Event、Graph、Gate、Permission、demo snapshot | 未做 PostgreSQL/API 集成测试；未被 Web 调用 | `apps/api/app/api/router.py` |
| 数据模型 | SQLAlchemy 模型与初始 Alembic migration | PostgreSQL 在线 migration、约束、事务和并发未验证；AgentHandoff、VerifiedFact、Assumption、Iteration、Feedback 尚无模型 | `apps/api/app/domain/models.py`、migration |
| 控制逻辑 | 阶段转移、G0-G6 映射、后端→前端、权限三态、Task 环检测纯函数 | 数据库原子认领、Run 恢复、副作用对账、Tool Policy 执行器未实现/未集成 | `control_plane.py`、pytest |
| Agent Runtime | `langgraph` 依赖已锁定 | LangGraph 图、Agent Loop、Context Pack Builder 运行时均未实现 | `pyproject.toml` 与代码目录 |
| 模型 | 规格锁定 DeepSeek 单供应商 | 渠道、模型名、Base URL、认证、流式、工具调用、Schema、长中文、限流/费用均未冒烟 | 配置字段为空；无 Adapter/真实样本 |
| Builder | 本机 Codex CLI 路径/版本曾检测并写入配置 | Codex CLI Adapter、受限工作区、路径/权限/恢复测试未实现 | `config.py`；无 adapter 代码 |
| 发布 | 无 | PostgreSQL 服务、内网部署、真实 URL、备份/恢复、种子内测、商业 BRD/G6 均不存在 | 项目文件与交接核验 |

## 3. 2026-08-20 可重复命令结果

| 命令 | 结果 | 只能证明 |
|---|---|---|
| `env CI=true pnpm check` | ESLint、TypeScript、Vitest 2/2、Ruff、pytest 12/12 通过 | 静态检查、demo 数据测试和确定性纯逻辑测试通过 |
| `env CI=true NEXT_TELEMETRY_DISABLED=1 pnpm build` | Next.js 16.3.1 production build 通过 | 页面代码可构建；不证明 API、交互或浏览器验收 |
| `alembic upgrade --sql head` | PostgreSQL dialect 离线 SQL 生成成功 | migration 可编译为 SQL；不证明真实数据库执行成功 |

## 4. 浏览器与截图口径

- `app-desktop.png`、`app-mobile.png`：D3 静态 mock 壳历史快照。
- `lifecycle-desktop.png`、`lifecycle-mobile.png`：生命周期阅读页历史快照。
- `harness-mobile.png`：单一原型页面的历史移动快照。
- 这些文件来自不同对象，不能拼接为“权威原型与 D3 应用交互一致”的证据。
- 本次没有形成可复现的 `1440×900`、`390×844` 完整交互记录，因此浏览器符合性状态为 **未验收**。

## 5. 阶段结论

- D1-D2：规格已冻结并获用户批准；规格语义一致性通过。
- D3：已开始，骨架/模型/API 定义/migration/mock 壳存在；退出条件未满足。
- D4：未开始。当前静态 mock 尚未打通 API → 群聊/状态 → Artifact DAG，也未实现批准的双栏交互。
- D5 及以后：未开始；DeepSeek 不得用 mock 放行。

## 6. 后续交接硬规则

1. 每个“已完成”必须同时写清证据对象、命令/页面、覆盖范围和未覆盖范围。
2. mock、静态截图和构建成功不得升级为真实 API、模型、数据库、交互或用户验收。
3. 根目录交互基线不能被 D3 简化壳或生命周期投影反向修改。
4. 新增/实质更新的用户阅读 Markdown 必须同步同名 HTML；未实际浏览器预览时明确写“未验证”。
