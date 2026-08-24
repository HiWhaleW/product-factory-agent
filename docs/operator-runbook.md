# 产品工厂 Agent - 开发与运维手册

> 同步日期：2026-08-24  
> 平台状态：产品工厂 Agent 本机双环境已建立；下一步是 GitHub 更新和火山引擎 `user-beta`。  
> 示范项目状态：销售复盘 Agent 为 `seed_beta / Context v10 / iteration v1`；G5 已批准，G6 尚未打开。  
> 环境拓扑：[双环境运行说明](./environments.html)

## 1. 当前运行基线

| 项目 | 当前事实 |
|---|---|
| Web | Next.js 16.3.1 / React 19.2.8 / Tailwind 4.3.3 |
| API | FastAPI 0.141.1 / Pydantic 2.13.4 |
| Runtime | LangGraph 1.2.11 / DeepSeek / 博查 / Codex CLI Adapter |
| 数据库 | PostgreSQL 16.15 / Alembic `20260823_0010 (head)` |
| 测试 | Web 34/34、Python 94/94（48 skipped）、PostgreSQL 48/48 |
| 构建 | production build、ESLint、TypeScript、Ruff 通过 |
| 销售复盘 Agent Gate | G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a` approved；G6 未打开；不阻塞平台 `user-beta` |

保留 1 条 Starlette/httpx 弃用警告。AG-UI/SSE 已是主通道；`2500ms` cursor 轮询只在断线时降级，SSE 自动恢复后停止。认证强制执行已完成，生产环境缺少认证配置会拒绝启动。

当前内部 current 为可重现 standalone 发布包 `20260824T074916Z`，previous 为 `20260824T042123Z`；独立用户环境 current 仍为 `20260824T042412Z-identity-only`，previous 为 `20260824T032335Z-settings-only`，数据库为 `20260823_0010`。`074916Z` 的 SHA-256 manifest 在启动核验前后保持一致；它尚未绑定或重新验收到用户环境。下一执行任务是先用 GitHub Connector 更新 Draft PR，再建立火山引擎 `user-beta` 环境。

`user-beta` 是产品工厂平台的真实用户测试环境，不需销售复盘 Agent G6。该示范项目的 G6 只约束其自身从种子内测进入正式发布。

## 2. 启动前检查

1. 读取 `AGENTS.md`、`README.md`、`docs/handoff.md`。
2. 检查 `git status`，保留已有修改。
3. 检查 PostgreSQL 16.15、Alembic head、Artifact Root、Workspace Root 和 `CODEX_CLI_PATH`。
4. 确认密钥只存在后端环境，不进入前端、仓库、日志、Context Pack 或 Artifact。
5. 任何 GitHub 远端写入前，用 Connector 核验当前 head 和 Draft PR #1；不得使用 `gh`。
6. 读取 [GitHub 与火山引擎用户测试环境交接](./cloud-user-beta-handoff.html)；不得从不可重现的手工混合发布包直接上云。

## 3. 标准命令

```bash
env UV_CACHE_DIR=.uv-cache uv sync --locked
pnpm install --frozen-lockfile
env CI=true pnpm check
pnpm test:api:integration
env CI=true NEXT_TELEMETRY_DISABLED=1 pnpm build
env UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini current

# 仅开发模式，在两个终端分别运行；不代表双 production 环境
pnpm dev:api
pnpm dev:web
```

普通 Python 单测不会隐式运行在线 PostgreSQL 集成测试；集成测试必须使用 `pnpm test:api:integration` 单独执行。

不要在主库执行 downgrade。migration 往返测试必须使用临时空库。

`pnpm db:status` 只检查仓库 `.runtime/postgresql-data` 中的 bundled PostgreSQL，不能代表 `.env` 实际指向的数据库。两套运行环境的真实状态应以 Alembic `current` 及各自 `preflight` 为准。

### 3.1 内部验证环境

```bash
scripts/seed-beta/configure.sh
scripts/seed-beta/release.sh
scripts/seed-beta/start.sh
scripts/seed-beta/health-check.sh
scripts/seed-beta/backup.sh
scripts/seed-beta/restore-check.sh
scripts/seed-beta/rollback.sh
scripts/seed-beta/stop.sh
```

内部凭据、PID、日志、发布包和备份只保存在被 Git 忽略的 `.runtime/seed-beta/`。该环境保留销售复盘 Agent 与内部验收数据。`restore-check.sh` 只恢复到固定前缀临时数据库，核对后删除，不修改主库。`rollback.sh` 只切换受控 current/previous 发布包，不覆盖工作区源码。

`release.sh` 从当前源码重建 Next.js standalone 产物，显式打包 API、Alembic 0001–0010、4 份冻结 Prompt 和依赖锁文件，并生成 SHA-256 完整性清单。包内不得出现绝对 `node_modules` 软链接、`.next/dev`、`.next/cache`、source map、`__pycache__` 或本机路径。新包启动前会重新校验完整性；旧包仅保留为本机受控回滚点，不能作为上云源码基线。

当前 `20260824T074916Z` 已完成打包与启动后 manifest 复核，启动没有改写发布内容。该结论只覆盖内部可重现基线，不代表独立用户环境已绑定、已重新验收或云上 `user-beta` 已完成。

### 3.2 独立用户环境

```bash
scripts/user-beta/configure.sh
scripts/user-beta/release.sh
scripts/user-beta/start.sh
scripts/user-beta/health-check.sh
scripts/user-beta/acceptance.sh
scripts/user-beta/backup.sh
scripts/user-beta/restore-check.sh
scripts/user-beta/rollback.sh
scripts/user-beta/stop.sh
```

用户环境固定使用独立数据库 `product_factory_user_beta` 和 `.runtime/user-beta/` 下的 Artifact、Workspace、日志、PID、备份与密钥。`release.sh` 只能绑定内部环境已经生成并验收通过的 `current` 发布包。`acceptance.sh` 必须验证真实用户已记录、项目列表为空、内部项目未泄露。

`rollback.sh` 只接受经 canonical path 校验后位于 `.runtime/seed-beta/releases/` 或 `.runtime/user-beta/releases/` 的受控发布包，以兼容新的内部同版本绑定与现有两个用户回滚点；其他目录、路径逃逸或无效链接一律 fail closed。

用户环境 current 为 `20260824T042412Z-identity-only`，previous 为 `20260824T032335Z-settings-only`；本机回滚边界已存在。云上 `user-beta` 仍必须单独建立发布版本、备份与回滚点，不得依赖本机 `.runtime` 指针。

## 4. 本地配置

```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg://...
ARTIFACT_ROOT=/absolute/approved/path
WORKSPACE_ROOT=/absolute/approved/path
USER_SECRET_ROOT=/absolute/approved/path/user-secrets

MODEL_PROVIDER=deepseek
MODEL_NAME=
MODEL_BASE_URL=
MODEL_API_KEY_REF=DEEPSEEK_API_KEY
DEEPSEEK_API_KEY=

WEB_RESEARCH_PROVIDER=bocha
WEB_RESEARCH_BASE_URL=https://api.bochaai.com/v1
WEB_RESEARCH_API_KEY_REF=BOCHA_API_KEY
BOCHA_API_KEY=

CODEX_CLI_PATH=/absolute/path/to/codex
CODEX_MAX_CONCURRENT_RUNS=1
CODEX_TASK_TIMEOUT_SECONDS=1800

INVITE_CODE_HASH=
SESSION_SECRET=
AUTH_ENFORCED=false
SESSION_TTL_SECONDS=28800

EVENT_STREAM_POLL_INTERVAL_SECONDS=0.5
EVENT_STREAM_HEARTBEAT_SECONDS=15
```

文档只能写变量名和 SecretRef，不能写真实密钥。

用户 API Key 由设置页写入 `USER_SECRET_ROOT`，根目录/用户目录权限必须为 `0700`，Key 文件权限必须为 `0600`。PostgreSQL 的 `user_provider_credentials` 保存 SecretRef、SHA-256 指纹、脱敏尾号及非敏感的接口名称/HTTPS Base URL/模型名。Runtime 使用用户配置的 OpenAI-compatible 接口；普通用户没有 Key 时 Agent 必须拒绝执行；`DEEPSEEK_API_KEY` 仅供内部验证账号测试回退，不能下发给普通用户。

生产环境必须设置 `AUTH_ENFORCED=true`，并配置 SHA-256 邀请码哈希与 Session Secret。Session 只通过 HttpOnly Cookie 传递；不要把令牌或邀请码写入前端环境变量。

## 5. 当前业务操作边界

- G5 已由用户批准，当前允许使用真实用户、真实任务和明确退出阈值开展内测，不能用 mock 数据。
- 销售复盘 Agent 的内测证据达标后才能生成该项目商业 BRD 并打开该项目 G6。
- 销售复盘 Agent G6 未批准前不得宣布该示范项目正式发布或商业交接。火山引擎 `user-beta` 是产品工厂平台的测试环境，不需该 G6。
- 前端现有内容默认固定；确需修改必须提前告诉用户。
- 冻结的 4 份 Agent Prompt 不得修改。
- 新版本必须先在内部环境完成迁移、测试、build、健康和浏览器验收，再发布到独立用户环境。
- 两套环境不得共享数据库、Artifact、Workspace、日志、Session Secret 或邀请码。
- 项目删除必须进入按 Session owner 隔离的回收箱；恢复回到删除前阶段并写入审计事件，重复恢复保持幂等。V1 不提供永久删除，Run、Gate、Artifact、Context 和审计链必须保留。

## 6. 浏览器检查

每次前端变更后至少检查桌面 `1440×900`、移动 `390×844` 和用户标注视口。当前最新额外检查为 `819×749`，warning/error 为 0。

重点检查：

- 阶段点击能跳到对应产物和该阶段聊天开头。
- 主 Agent 邀请子 Agent，子 Agent 入群后自我介绍。
- 执行过程显示在用户消息与 Agent 回复之间。
- 工具过程使用普通人能懂的中文，不显示杂乱技术事件。
- 时间、标题和说明不遮挡。
- 无限画布缩放无黑框动效。
- 未登录访问受保护 API 返回 401，首页只显示邀请码登录。
- 登录后 `/events/stream` 保持 `text/event-stream` 长连接；断线显示降级提示并启动轮询，SSE 恢复后提示消失且轮询停止。

## 7. 排障

| 现象 | 先检查 | 不要做 |
|---|---|---|
| 页面状态和数据库不一致 | Project/Event/Gate/Artifact 真相源 | 不在前端写假状态 |
| Agent 使用旧事实 | ContextVersion、stale handoff | 不拼接新旧草稿 |
| Gate 重复执行 | Gate ID、ContextVersion、幂等键 | 不盲目重试 |
| Codex 越工作区 | 解析后路径、软链接、Tool Policy | 不靠 Prompt 自律 |
| 页面显示完成但无证据 | RunStep、ArtifactVersion、测试、Gate | 不降低验收 |
| 日志出现密钥 | 立即停止、脱敏、轮换 | 不继续传播日志 |
| 用户首页出现内部项目 | 检查用户数据库、Session 用户和 owner 过滤 | 不在前端隐藏泄露结果冒充隔离 |
| 用户环境发布失败 | 保持原 current，检查内部发布包和 preflight | 不直接从工作区启动未验收代码 |

## 8. 发布边界

- 当前 V1 已在本机/内网跑通；下一步是火山引擎受控用户测试环境。
- Builder 禁止自动 push、deploy 或删除工作区。
- GitHub 只用 Connector；写入前重新核验 Draft PR head，使用 `force:false`，保持 Draft 且不 merge。
- 云上必须使用独立 PostgreSQL、Artifact/Workspace、日志、Secret Store、Session Secret 和邀请哈希；不复制本地或内部秘密。
- 不得把带本地 Codex CLI 和本地工作区能力的 Builder 直接暴露到公开 veFaaS 函数。
- 销售复盘 Agent 正式发布必须等待该项目真实种子内测、商业 BRD 和 G6；平台 `user-beta` 不在此阻断条件内。
- 发布后必须保存 Deployment Record、真实 URL、健康检查、回滚方案和反馈分支。
- `http://127.0.0.1:3200` / `8200` 是内部验证环境；`http://127.0.0.1:3300` / `8300` 是独立用户环境。
- 两套地址目前都是本机回环 URL；跨设备或公网访问前必须配置受信任 HTTPS、production Cookie 策略和独立部署边界。
- 云上环境必须在邀请真实用户前完成 HTTPS、健康、强制认证、SSE、空项目隔离、Secret Store、备份/恢复、回滚和真实浏览器 QA。
