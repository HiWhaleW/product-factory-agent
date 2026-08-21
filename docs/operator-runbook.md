# 产品工厂 Agent - 开发/运维交接

> 同步日期：2026-08-22  
> 当前状态：D3–D4 已收口，D5 进行中；PostgreSQL migration `20260822_0004`、DeepSeek/博查 Runtime、Factory Lead 和 AI PM→Reviewer→G1 确定性后端契约已存在；隔离真实 Reviewer/G1 open 纵向冒烟已通过，真实产品 G0/G1、Builder 和部署未完成。

## 1. 本机已检测环境

| 工具 | 路径/版本 | 判断 |
|---|---|---|
| Codex CLI | `CODEX_CLI_PATH` / `0.148.0-alpha.15` | 可用；路径由环境变量配置，不硬编码 |
| Node.js | `PATH` / `24.19.0` | 可用 |
| npm | `PATH` / `10.9.8` | 可用 |
| pnpm | 本机可用，项目已生成 `pnpm-lock.yaml` | 依赖已锁定；构建脚本仅允许必要原生依赖脚本 |
| uv | `PATH` / `0.12.1` | 可用 |
| 项目 Python | `.venv` / `3.12.13` | 由 uv 管理；不用系统 Python 3.9.6 |
| Docker | 未检测到 | 不阻塞 V1；V2 沙箱化再引入 |
| Git | 已初始化，分支 `main` | 当前文件尚未创建基线 commit |

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

PostgreSQL 16.15、Artifact/Workspace Root 和 Codex CLI 已在本机配置并验证：根目录 `artifacts/` 与 `workspaces/` 相互独立且被 Git 忽略，Codex CLI 路径存在、可执行并返回 `0.148.0-alpha.15`。DeepSeek 渠道、`MODEL_NAME`、`MODEL_BASE_URL` 最晚 D5 真模型切片前就绪；正式发布宿主机/URL 在 B1-Bn 真实内测证据达标、G6 前就绪。

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
4. [完成] PostgreSQL 16.15 在线，migration 到 20260822_0004 (head)，Artifact/Workspace/Codex 路径已验证
5. [完成基础切片] Project/Message/Event/Graph/Gate/Permission API 与 Task 原子认领
6. [完成基础切片] 状态迁移、Permission 不推进阶段、过期/旧 Context 拒绝和并发幂等
7. [完成基础切片] 真实单屏 UI 展示 12 阶段、群聊、Gate/Permission 与 React Flow Artifact DAG
8. [已验证] PostgreSQL 集成 42/42；DeepSeek/博查/Factory Lead/隔离 AI PM→Reviewer→G1 open 真实冒烟已有脱敏证据
9. [待完成] 真实产品 G0/G1 用户决定；Codex Builder 与完整 AG-UI/浏览器恢复
```

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

末次验证记录（2026-08-22）：`pnpm check` 为 Web 6/6、Python 52/52；`pnpm test:api:integration` 在允许访问本机 PostgreSQL 后为 42/42；Alembic 为 `20260822_0004 (head)`。保留 1 条 Starlette/httpx 弃用警告。第一次在受限环境运行在线测试出现 31 failed / 40 errors，根因是系统禁止访问本机 PostgreSQL，允许访问后重跑全部通过。

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
