# 产品工厂 Agent - 开发/运维交接

> 同步日期：2026-08-23  
> 当前状态：D3–D4 已收口，D5 进行中；PostgreSQL migration `20260822_0006`、DeepSeek/博查 Runtime、Factory Lead 和 AI PM→Reviewer→G1 确定性后端契约已存在；“销售复盘 Agent”为 `prd / Context v3 / iteration v1` 并已投影到 Web；PRD/G2、Builder 和部署未完成。

## 1. 本机已检测环境

| 工具 | 路径/版本 | 判断 |
|---|---|---|
| Codex CLI | `CODEX_CLI_PATH` / 当前运行态 `0.148.0-alpha.21` | 可用；D3–D4 历史证据为 `.15`，路径由环境变量配置，不硬编码 |
| Node.js | `PATH` / `24.19.0` | 可用 |
| npm | `PATH` / `10.9.8` | 可用 |
| pnpm | 本机可用，项目已生成 `pnpm-lock.yaml` | 依赖已锁定；构建脚本仅允许必要原生依赖脚本 |
| uv | `PATH` / `0.12.1` | 可用 |
| 项目 Python | `.venv` / `3.12.13` | 由 uv 管理；不用系统 Python 3.9.6 |
| Docker | 未检测到 | 不阻塞 V1；V2 沙箱化再引入 |
| Git | 本地已初始化；`origin` 指向 `https://github.com/HiWhaleW/product-factory-agent.git` | Connector 已将 `codex/initial-import` 以 `force:false` 快进到 `db39b5dd…`；Draft PR #1 仍 open/draft；本地 main 仍无 commit |

## 2. 当前可打开的静态产物

不需要服务器：

- `产品工厂Agent_Harness表.html`（唯一权威交互视觉基线）
- `产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html`（12 阶段生命周期适配投影，不替代视觉基线）
- `产品工厂Agent/spec/index.html`
- `docs/handoff.html`

它们是交互/规格/交接可视化，不会启动 Agent、修改数据库或调用外部 API。

## 3. Spec Freeze 批准记录

- [x] Spec Freeze Review 通过。
- [x] V1 仅单用户/单管理员。
- [x] V1 仅 DeepSeek 一个模型供应商；接入渠道、模型名和 Base URL 最晚 D5 真模型切片前锁定并真实冒烟。
- [x] V1 Builder 使用本地 Codex CLI。
- [x] V1 本机/内网运行，不引入 SSO、多租户或云代码沙箱。

## 4. 分阶段环境值

PostgreSQL 16.15、Artifact/Workspace Root 和 Codex CLI 已在本机配置并验证：根目录 `artifacts/` 与 `workspaces/` 相互独立且被 Git 忽略，Codex CLI 路径存在、可执行；D3–D4 历史证据记录 `0.148.0-alpha.15`，2026-08-22 设置页运行态检测为 `0.148.0-alpha.21`。DeepSeek 渠道、`MODEL_NAME`、`MODEL_BASE_URL` 已配置并完成脱敏真实冒烟；正式发布宿主机/URL 在 B1-Bn 真实内测证据达标、G6 前就绪。

```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg://...
ARTIFACT_ROOT=/absolute/approved/path
WORKSPACE_ROOT=/absolute/approved/path

MODEL_PROVIDER=deepseek
MODEL_NAME=
MODEL_BASE_URL=
MODEL_API_KEY_REF=DEEPSEEK_API_KEY
DEEPSEEK_API_KEY=

WEB_RESEARCH_PROVIDER=bocha
WEB_RESEARCH_BASE_URL=https://api.bochaai.com/v1
WEB_RESEARCH_API_KEY_REF=BOCHA_API_KEY
WEB_RESEARCH_TIMEOUT_SECONDS=30
BOCHA_API_KEY=

CODEX_CLI_PATH=/absolute/path/to/codex
CODEX_MAX_CONCURRENT_RUNS=1
CODEX_TASK_TIMEOUT_SECONDS=1800

INVITE_CODE_HASH=
SESSION_SECRET=
```

密钥值不写进文档、群聊、Prompt、命令输出或 Git，也不要求用户在聊天中粘贴；只在批准的后端 Secret 管理位置配置并传递 SecretRef。

## 5. D3-D4 执行与剩余顺序

详细每日工程排期、依赖和退出证据以 [Engineering-Schedule.md](../产品工厂Agent/spec/Engineering-Schedule.md) 为准；本节仅保留环境/运维顺序摘要。

```text
1. [完成] 初始化 Git，保留用户已有文件
2. [完成] 用 uv 安装/锁定 Python 3.12
3. [完成] 创建 Next.js + FastAPI monorepo 骨架
4. [完成] PostgreSQL 16.15 在线，migration 到 20260822_0006 (head)，Artifact/Workspace/Codex 路径已验证
5. [完成基础切片] Project/Message/Event/Graph/Gate/Permission API 与 Task 原子认领
6. [完成基础切片] 状态迁移、Permission 不推进阶段、过期/旧 Context 拒绝和并发幂等
7. [完成基础切片] 真实单屏 UI 展示 12 阶段、群聊、Gate/Permission 与 React Flow Artifact DAG
8. [已验证] PostgreSQL 集成 42/42；DeepSeek/博查/Factory Lead/AI PM→Reviewer 真实冒烟已有脱敏证据；销售复盘项目 G0/G1 已由用户决定
9. [完成并线] 销售复盘项目、Artifact v1/v2、历史 G1、执行/恢复投影和 Session 契约已接入 Web
10. [待完成] AI PM PRD Run、确定性 PRD 持久化、G2；Codex Builder 与完整 AG-UI/浏览器恢复
```

### 5.1 正式接手的 GitHub 操作边界

- 远端读取、分支、提交/文件上传和 PR 更新必须使用 GitHub 插件/Connector，不得使用 `gh` CLI。
- Connector 已核验默认分支 `main`、`codex/initial-import` 和 open Draft PR #1；推送前再次核对 PR head，使用 `force:false`。
- 推送前按 `.gitignore`、秘密和本机路径扫描形成安全清单；不得上传 `.env`、Runtime、虚拟环境、依赖/缓存、Artifact/Workspace 或 SecretRef 原值。
- 不得 force push、重建仓库或覆盖其他任务线。插件缺失或无写权限时停止远端写入并请求安装/授权。

## 6. 当前标准检查命令

以下命令当前可执行；在线 PostgreSQL 测试必须使用专用命令，不由普通 pytest 隐式运行：

```bash
env UV_CACHE_DIR=.uv-cache uv sync --locked
pnpm install --frozen-lockfile
env CI=true pnpm check
env CI=true NEXT_TELEMETRY_DISABLED=1 pnpm build
pnpm test:api:integration
env UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini current
pnpm dev
```

本轮 migration 往返命令：

```bash
env UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini downgrade 20260822_0003
pnpm db:migrate
```

Reviewer 对接字段和错误码见 [D5 AI PM→Reviewer→G1 契约](./contracts/d5-review-candidate-contract-2026-08-22.md)。

Runtime/后端已把“销售复盘 Agent”恢复到 Web 同源 API，并提供 Evidence Index v2、MRD v2、Red Team Review v2、G1 两项 known issues、Artifact 版本索引、`gate-decisions` 用户批准记录、真实 membership/run/task/step/tool/recovery 投影与 Session 契约。完整读取接口见 [D5 Web / 后端真实投影契约](./contracts/d5-web-backend-projection-contract-2026-08-23.md)。仍缺专用可回收 Gate/Permission 样本、认证强制执行和 AG-UI/SSE；`2500ms` cursor 轮询仍是降级。“D3 双栏交互验收”仅可用于前端回归。

末次验证记录（2026-08-23）：Web ESLint、TypeScript、Vitest 13/13 通过；Ruff 与 Python 56/56 通过；PostgreSQL 集成 42/42；主库 Alembic 为 `20260822_0006 (head)`。临时空库的 `upgrade head → downgrade 0004 → upgrade head` 通过；测试先发现并修复空库恢复事件外键和破坏性降级两项问题。保留 1 条 Starlette/httpx 弃用警告。受限沙箱内的本机 TCP 失败不计为断言失败，授权连接 PostgreSQL 后全部通过。

并行 Runtime 线随后新增 PRD 路由；当前工作区最新一次 `pnpm check` 因其独立 `apps/api/app/api/agent_router.py` 导入顺序失败。本线未覆盖该文件。Runtime 线收口后需要重新运行 `pnpm check`，此前通过记录不能冒充最新全工作区结果。

## 7. D9-D10 内部验收与发布前健康检查

D9-D10 只完成内部 QA 和 G5/Beta Candidate，必须包含：

- 本机/内网访问控制、数据归属；正式 HTTPS/发布目标在 G6 前确认。
- PostgreSQL 备份和恢复。
- Artifact Store 原子写入、哈希、路径逃逸防护和内容消毒。
- Agent 事件断线/cursor 恢复。
- 工具超时、预算、重试和幂等。
- 真实模型冒烟、真实浏览器 QA 和 G5 内部验收。
- 真实种子内测与商业 BRD/G6 未通过前禁止正式发布。

## 8. 已知风险/排障路由

| 现象 | 首先检查 | 不要做 |
|---|---|---|
| Agent 使用旧事实 | Context Pack `contextVersion`、已批决定和 stale handoff | 不手工将新老草稿拼成一份 |
| 审批重复执行 | `gate_id + context_version` 幂等键 | 不盲目重试发布/计费动作 |
| DAG 缺节点 | Artifact/Event 后端事实 | 不只修前端画布状态 |
| Codex 越工作区 | 解析后路径、软链接、Tool Policy | 不靠 Prompt “请不要越界” |
| 页面显示完成但无产物 | ArtifactVersion/测试/人工闸证据 | 不降低完成定义 |
| 密钥出现在日志 | 立即停止、脱敏并轮换密钥 | 不把日志继续传入 Agent |

## 9. 部署边界

- V1 本机/内网运行 Web、API、PostgreSQL 和 Codex CLI Adapter。
- 根目录 veFaaS 手册只作将来 Web/API 部署参考；不用 veFaaS 函数运行本地 Builder 工作区。
- V2 再评估 OpenHands/ACP/E2B/企业 Docker/Kubernetes 沙箱。
