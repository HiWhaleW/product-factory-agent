# 产品工厂 Agent - 本地开发与运维手册

> 同步日期：2026-08-25  
> 当前边界：只维护一套用户环境；旧 beta 环境已退出并归档

## 1. 当前入口

- Web：`http://127.0.0.1:3400`
- API：`http://127.0.0.1:8400`
- 当前配置：`.runtime/user-preview/user-preview.env`
- 当前持久化根：`.runtime/user-preview/`
- 当前 PostgreSQL：`.runtime/user-preview/postgresql-16.15/` 与 `.runtime/user-preview/postgresql-data/`

上述地址是当前唯一运行入口，也是用户在本机浏览器中实际使用的网站。

## 2. 开工前检查

```bash
pwd
git status --short
rg --files apps/api/alembic/versions | sort
env CI=true pnpm check
pnpm test:api:integration
env CI=true NEXT_TELEMETRY_DISABLED=1 pnpm build
```

- 在线 PostgreSQL 集成测试必须使用独立临时数据库，不得直接对用户预览数据库执行。
- migration downgrade 只允许在临时空库演练。
- 不打印 `.env`、Session Secret、API Key 或数据库连接串。
- 不将 `.runtime`、`.next`、日志、备份或用户数据加入 Git。

## 3. 当前开发预览

API 和 Web 使用同一用户预览配置。启动前确认 3400/8400 是否已有进程，避免重复绑定。

API 等价启动方式：

```bash
set -a
source .runtime/user-preview/user-preview.env
set +a
export PYTHONPATH=apps/api
env UV_CACHE_DIR=.uv-cache .venv/bin/uvicorn app.main:app --app-dir apps/api \
  --host 127.0.0.1 --port 8400
```

Web 等价启动方式：

```bash
set -a
source .runtime/user-preview/user-preview.env
set +a
export PRODUCT_FACTORY_API_URL=http://127.0.0.1:8400
pnpm --dir apps/web dev --hostname 127.0.0.1 --port 3400
```

根 `.env` 是指向 `.runtime/user-preview/user-preview.env` 的本机符号链接，避免出现第二套默认数据库或文件目录。启动前以端口监听和实际命令为准，不盲信历史 PID 文件。

## 4. 健康与安全检查

```bash
curl -fsS http://127.0.0.1:8400/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3400/
env UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini current
```

还要检查：

- 未登录访问受保护 API 会 fail closed。
- 登录 Cookie 为 HttpOnly；production 安装时配置 Secure。
- SSE 正常连接；断线时才启动短轮询，恢复后停止。
- 用户 A 无法读取用户 B 项目。
- API Key 回包、日志、数据库和 Artifact 中没有原文。
- 页面在 `1440×900` 和 `390×844` 无横向滚动。

## 5. 当前账户与 API

- 首次打开由用户创建企业本地账户，不使用邀请码。
- 第一个有效注册账户为管理员；后续账户为普通用户。
- 大模型 API 和网络搜索 API 默认空。
- 大模型支持 OpenAI-compatible HTTPS API。
- 网络搜索当前只有博查官方接口能真实执行；其他厂商配置可保存但运行时拒绝调用。
- 用户未配置有效模型 API 时，Agent 任务应停止并给出通俗提示，不得回退到产品方 Key。

## 6. Docker Compose 本地安装

安装包入口：`compose.yaml`、`apps/api/Dockerfile`、`apps/web/Dockerfile`、`scripts/install/` 和 [本地安装说明](./installation.html)。

```bash
./scripts/install/install.sh
./scripts/install/health.sh
./scripts/install/backup.sh
./scripts/install/restore-check.sh <backup-id>
```

- 安装配置写入 `.product-factory/install.env`，权限 `0600`，不会提交到 Git。
- 默认只暴露 `127.0.0.1:3400`；API 和 PostgreSQL 只在 Compose 网络内访问。
- 模型和搜索 API 均为空；Builder 默认禁用，不挂载宿主机或 Docker Socket。
- PostgreSQL、Artifact、Workspace、Secret Store 和日志使用命名卷。
- 恢复检查使用独立 Compose project 和独立数据卷，退出时删除检查环境，不改当前安装。
- 当前主机没有容器运行时，所以只完成了静态契约与源码回归；**Compose 真实安装验收仍未完成**。这不是当前源码网页可用性的否定。

## 7. 本地归档

2026-08-25 已停止并退出旧 3200/8200 与 3300/8300 环境，旧数据库先生成可恢复 dump 后删除。旧运行目录、发布脚本、根 Artifact/Workspace 和内部材料已移出项目根目录，保存在维护者本机的外部归档区。

- 外部归档不属于代码工作区、Git 基线或 Docker 构建上下文。
- 归档可能含历史用户数据和秘密，只能保留在本机，不得公开上传。
- 当前运行环境不读取该归档。
- 是否永久删除归档是后续独立的破坏性决定。

## 8. 当前验证基线

- Web 39/39。
- Python 104 passed / 48 skipped；归档的 7 个旧发布链测试不再计入主线。
- production build、ESLint、TypeScript、Ruff 通过。
- 敏感信息扫描未发现私钥、常见真实 Provider Token、本机绝对路径或当前/历史本机秘密进入公开源码范围。
- 保留 1 条 Starlette/httpx 弃用警告。
- Alembic `20260824_0011 (head)`。
- 本地 `main` 已建立正式源码初始基线；运行数据、外部归档和内部 Agent 指令不进入该基线。
