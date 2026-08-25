<h1 align="center">造物工场</h1>

<p align="center">
  一个本地优先的 AI Native 产品交付 Agent。<br>
  用户只需要说清想做什么，Agent 会围绕 Context、工具、产物、Reviewer 和人工 Gate 推进工作。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/AI--Native-Agent%20Product-0B57D0?style=flat-square" alt="AI Native Agent Product">
  <img src="https://img.shields.io/badge/Next.js-16-111111?style=flat-square&logo=nextdotjs" alt="Next.js 16">
  <img src="https://img.shields.io/badge/FastAPI-0.141-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/deployment-local--first-D6A313?style=flat-square" alt="Local first">
  <img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-D84A3A?style=flat-square" alt="PolyForm Noncommercial License 1.0.0">
</p>

<p align="center">
  <a href="#产品概览"><strong>产品概览</strong></a>
  ·
  <a href="#当前发布状态"><strong>当前发布状态</strong></a>
  ·
  <a href="#本地运行"><strong>本地运行</strong></a>
  ·
  <a href="#许可证"><strong>许可证</strong></a>
</p>

> [!NOTE]
> 产品工厂 Agent 是本地 Web 应用。Web、API、PostgreSQL、项目文件与用户凭据运行在使用者自己的电脑；启动后通过浏览器访问 `http://127.0.0.1:3400`。它不是由项目维护者提供的公共 SaaS 网站。

> [!WARNING]
> 产品不内置大模型或网络搜索 API。使用者需要在设置页自行配置；未配置时相关 Agent 任务会明确停止，不会使用隐藏的产品方 Key，也不会伪造结果。

> [!IMPORTANT]
> Gate 只能由用户批准。模型不能自行推进业务阶段、扩大工具权限、发布代码或删除项目工作区。

## 当前发布状态

以下事实于 2026-08-25 完成源码发布时核验：

| 对象 | 当前事实 |
| --- | --- |
| 本机源码预览 | Web `127.0.0.1:3400` 与 API `127.0.0.1:8400` 在线，健康检查通过；Alembic 为 `20260824_0011 (head)`；用户模型 API 尚未配置。 |
| 本地 Git | `main` 已建立清理后的正式源码基线；运行数据、外部归档和内部 Agent 指令不在版本基线中。 |
| GitHub 仓库 | `HiWhaleW/product-factory-agent` 的 `main` 收录完整源码、安装脚本、测试、文档和 `LICENSE`；仓库当前仍为私有，仅获授权的账号可以克隆。 |
| 发布方式 | 本次完整源码通过 [PR #2](https://github.com/HiWhaleW/product-factory-agent/pull/2) 合并进入 `main`，不依赖维护者本机的运行数据或历史归档。 |
| 历史基线 | 2026-08-24 的旧 user-beta PR 不是当前开源源码基线，不得反向覆盖当前 `main`。 |
| Compose 安装 | 安装契约和脚本已实现，但当前维护者电脑没有兼容容器运行时，真实镜像构建与干净环境安装验收尚未完成。 |

因此，当前状态是“完整源码已进入 GitHub `main`，本机源码运行与自动化检查通过，Compose 实机安装尚未验收”。仓库仍为私有时，外部使用者无法下载；改为公开仓库后，使用者可按下方说明在自己的电脑安装并通过浏览器使用。

## 产品概览

造物工场希望解决的不是“给固定工作流加一个聊天框”，而是让 Agent 真正成为产品工作的执行者。

用户用自然语言描述一个产品目标后，系统会：

1. 理解目标、识别缺失信息并提出范围问题；
2. 把已确认事实整理为结构化 Context；
3. 由主 Agent 创建任务，并把任务与必要 Context 交给专业 Agent；
4. 在权限、预算和项目 Gate 约束下调用工具；
5. 生成可持久化、可追溯、可版本化的 Artifact；
6. 由独立 Reviewer 审查证据、范围、风险与验收结果；
7. 把是否继续推进的决定交还用户；
8. 在修改、失败或中断后保留记录并支持恢复。

聊天消息不是产物，模型自述“完成”也不是完成。只有真实 Artifact、工具结果、测试证据、Reviewer 结论和用户 Gate 共同构成交付链路。

## 当前版本

- 本地账户注册、密码登录和 HttpOnly Session
- 按用户隔离的项目、消息、任务、Run、Gate、Artifact 与 API 配置
- 首页自然语言入口、项目列表、项目群聊和 Artifact 工作区
- Factory Lead、AI PM、Builder、Reviewer 四个核心 Agent
- 12 个产品阶段与 G0–G6 人工 Gate
- Context Version、Context Pack、Agent Task、RunStep 与恢复记录
- 用户可见 Artifact DAG 与内部 Execution Task DAG
- OpenAI-compatible 大模型配置
- 博查官方接口的网络搜索 Runtime 适配
- 用户隔离、权限 `0600` 的本机 Secret Store
- Docker Compose v2 本地安装、备份、恢复、升级、回滚和卸载脚本

当前不提供：公共 SaaS、内置模型额度、内置搜索额度、支付、自动 Git push、自动云部署，或不受控的宿主机 Builder 权限。

## AI Native 工作循环

```text
自然语言目标
→ 主 Agent 理解与追问
→ 结构化 Context
→ 用户 Gate
→ Agent 任务与最小必要 Context Pack
→ 受控工具调用
→ Artifact 与 RunStep 持久化
→ 独立 Reviewer
→ 用户决定继续、修改、暂停或终止
```

AI 的价值在于理解模糊目标、规划工作、生成候选方案、比较证据和处理反馈。确定性控制面负责身份归属、状态转移、Gate、权限、预算、幂等、审计和恢复。

## 核心体验

| 能力 | 用户得到什么 |
| --- | --- |
| 自然语言创建项目 | 不需要先把想法翻译成复杂表单或固定模板 |
| 主 Agent 主动追问 | 在真正影响范围的地方提问，不用无止境聊天代替推进 |
| 多 Agent 协作 | 子 Agent 入场时同时获得明确任务和必要 Context，而不是只做角色表演 |
| 累计 Artifact 工作区 | MRD、PRD、方案、技术文档、代码和 QA 证据按版本与依赖关系持续积累 |
| 人工 Gate | 每个关键业务推进点由用户决定，Agent 不代替用户批准 |
| Reviewer 独立审查 | 审查输入、证据和结论与生成 Agent 分离 |
| 可恢复执行 | 中断或失败后保留 RunStep、工具结果和幂等信息，不从头猜测状态 |
| 用户自带 API | 模型与搜索凭据由每个本地用户独立配置和保管 |

## AI 与确定性职责

| 模型负责 | 确定性系统负责 |
| --- | --- |
| 理解模糊自然语言 | 校验输入 Schema 与用户身份 |
| 提出澄清问题和候选计划 | 判断当前阶段允许哪些动作 |
| 选择建议调用的工具 | 执行 `allow / ask / deny` 权限策略 |
| 生成 MRD、PRD、方案或代码候选 | 保存 Artifact、版本、哈希和依赖关系 |
| 比较证据并起草审查意见 | 验证证据引用、预算、幂等和恢复条件 |
| 理解用户反馈并提出修订 | 只接受用户作出的 Gate 决策 |

模型输出不是事实真相，也不能绕过 Session、Gate、Tool Policy、Artifact 校验或 Reviewer。

## 本地运行

> [!CAUTION]
> 下列命令是仓库公开后的安装入口。仓库保持私有时，只有获授权的 GitHub 账号可以克隆；是否公开仓库由维护者另行决定。

### 前置条件

- Git
- 能提供 Docker Engine API 的兼容容器运行时
- Docker Compose v2，可执行 `docker compose version`
- 至少 4 GB 可用内存和 10 GB 可用磁盘
- `bash`、`openssl`、`curl`、`shasum`
- 本机端口 `3400` 未被占用

Docker Desktop 不是本项目的一部分。macOS、Windows 或 Linux 使用者可以自行选择兼容 Docker Engine 与 Compose v2 的运行时。

### 安装

```bash
git clone https://github.com/HiWhaleW/product-factory-agent.git
cd product-factory-agent
./scripts/install/install.sh
```

安装完成后打开：

```text
http://127.0.0.1:3400
```

首次打开时创建本地账户。第一个账户为本机管理员；新安装实例的项目列表为空。模型 API 和网络搜索 API 也为空，由用户在设置页填写。

常用命令：

```bash
./scripts/install/health.sh
./scripts/install/backup.sh
./scripts/install/stop.sh
./scripts/install/start.sh
./scripts/install/upgrade.sh
./scripts/install/rollback.sh
./scripts/install/uninstall.sh
```

备份与恢复的破坏性边界见 [本地安装说明](docs/installation.md)。

## 架构

- Next.js 16 / React 19 / Tailwind CSS 4
- FastAPI / Pydantic / SQLAlchemy
- PostgreSQL 16 / Alembic
- LangGraph 有界 Agent Run
- AG-UI / SSE 事件通道
- Factory Lead、AI PM、Builder、Reviewer
- 确定性状态机、Gate、权限与审计控制面
- 本地 Artifact Store、Workspace 和用户 Secret Store
- Docker Compose v2 本地安装拓扑

完整设计见 [架构说明](docs/architecture.md)。

## 验证

2026-08-25 本机重新核验结果：

- Web：39/39。
- Python：104 passed / 48 skipped；保留 1 条 Starlette/httpx 弃用警告。
- ESLint、TypeScript、Ruff 与 Next.js production build：通过。
- Web/API 健康检查：通过；Alembic：`20260824_0011 (head)`。
- PostgreSQL 集成测试需要独立临时数据库；默认测试中的 48 项集成测试本次保持 skipped。
- Docker Compose 实机安装、真实模型效果与首次公开 GitHub 安装：尚未验收。

```bash
pnpm install --frozen-lockfile
pnpm check
pnpm build
```

PostgreSQL 集成测试需要单独的临时测试数据库：

```bash
pnpm test:api:integration
```

真实模型验证需要使用者自己的 API 配置，并与确定性回归测试分开记录。

## 反馈与贡献

欢迎报告问题、补充文档和提交改进。仓库保持私有时，Issue、Fork 和 Pull Request 仅对获授权的 GitHub 账号开放；仓库公开后，任何遵守许可证与贡献要求的人都可以参与。

- 使用问题、Bug 或功能建议：提交 [Issue](https://github.com/HiWhaleW/product-factory-agent/issues)
- 已有修复或改进：提交 [Pull Request](https://github.com/HiWhaleW/product-factory-agent/pulls)
- 提交 PR 前请先说明问题、改动范围、验证结果和已知限制。
- 涉及页面变化时，请附桌面端与移动端截图或可复核录屏。
- 不要在 Issue、PR、截图、日志或测试数据中提交 API Key、Cookie、数据库连接串和真实用户数据。
- PR 只代表代码提议；是否合并、发布或改变产品 Gate 仍由项目维护者决定。

建议的贡献流程：

```bash
git checkout -b feature/your-change
pnpm check
pnpm build
git push your-fork feature/your-change
```

然后从你的 Fork 向本仓库提交 PR。

## 许可证

本项目采用 [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)。

该许可证允许在非商业目的下查看、使用、复制、修改和分发源码，包括个人学习、研究、非商业自用，以及为本项目 Fork、修改并提交 PR。

未经版权所有者另行书面授权，不得将本项目用于商业产品、收费服务、客户项目、SaaS、广告营销、商业培训或其他直接及间接营利活动。

使用、复制或分发时必须保留许可证要求的声明。完整法律条款以仓库中的 `LICENSE` 文件为准。

由于包含非商业限制，本项目属于 **source-available（源码可见）**，不是 OSI 定义下的标准开源软件。
