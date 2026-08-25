# 产品工厂 Agent - 本地安装

> 日期：2026-08-25  
> 状态：Docker Compose v2 安装契约已实现；当前维护者电脑未做容器实机验收

## 1. 边界

本安装包把产品工厂 Agent 的 Web、API 和 PostgreSQL 安装到使用者自己的电脑。安装后通过浏览器访问本地网站，不需要产品方提供公共服务器。它不会：

- 内置或索要大模型、搜索 API Key。
- 复制维护者电脑上的用户数据、`.runtime`、外部历史归档、日志或本机路径。
- 运行真实项目、生成 MRD、调用 Reviewer 或推进 Gate。
- 挂载宿主机根目录或 Docker Socket。
- 推送 GitHub、部署云端或创建付费资源。

Builder 默认禁用。API 会返回 `BUILDER_DISABLED`，不会伪装成可用。若未来要启用 Builder，必须另行设计受控 Codex CLI 镜像/挂载、项目级 Workspace 与验收，不允许直接扩大 Compose 权限。

## 2. 前置条件

- 能提供 Docker Engine API 的兼容容器运行时。
- Docker Compose v2，可执行 `docker compose version`。
- 至少 4 GB 可用内存、10 GB 可用磁盘。
- `bash`、`openssl`、`curl`、`shasum`。
- 默认端口 `127.0.0.1:3400` 未被占用。

默认配置只允许本机访问。不要仅把 `WEB_BIND_ADDRESS` 改成 `0.0.0.0` 就对内网开放；跨机器访问必须先配置企业 HTTPS 反向代理，并把 `APP_ENV` 切到 `production` 以启用 Secure Cookie。

Docker Desktop 不是仓库的一部分，也不是项目维护者上传源码的前置。macOS、Windows 或 Linux 使用者自行选择兼容运行时；当前官方脚本只承诺 Docker Compose v2。维护者电脑没有安装容器运行时，因此以下步骤尚未在该电脑做真实容器验收。

## 3. 一键安装

在项目根目录执行：

```bash
./scripts/install/install.sh
```

安装器会：

1. 检查 Docker Engine 与 Compose v2。
2. 创建 `.product-factory/install.env`，自动生成 PostgreSQL 密码和 Session Secret，并设置权限 `0600`。
3. 构建锁定版本的 API 与 Web 镜像。
4. 启动 PostgreSQL，等待健康后执行 Alembic `upgrade head`。
5. 启动 API 与 Web，并检查 Web、API、数据库和 migration head。

完成后打开 `http://127.0.0.1:3400`，创建第一个本地管理员账户。设置页的大模型和搜索 API 均应为空。

## 4. 日常操作

```bash
./scripts/install/start.sh
./scripts/install/health.sh
./scripts/install/stop.sh
```

API 日志同时写入 Docker 日志和 `application-logs` 命名卷，Web 日志写入同一命名卷。查看日志时不要把完整日志发送到公开渠道：

```bash
docker compose --env-file .product-factory/install.env -f compose.yaml logs --tail 200
```

## 5. 备份与恢复

创建一致性备份时，脚本会短暂停止 Web/API，数据库继续运行：

```bash
./scripts/install/backup.sh
```

备份位于 `.product-factory/backups/<backup-id>/`，包含数据库、Artifact、Workspace、Secret Store、应用日志和安装配置。它含用户数据和秘密，目录权限为 `0700`，文件为 `0600`。

先在隔离环境验证备份；该命令使用独立 Compose project、独立端口和独立数据卷，不修改当前安装：

```bash
./scripts/install/restore-check.sh <backup-id>
```

只有隔离恢复检查通过后，才可显式覆盖当前安装：

```bash
./scripts/install/restore.sh --confirm <backup-id>
```

`restore.sh` 会替换当前数据库与 Artifact、Workspace、Secret Store、应用日志四个数据卷中的内容，属于破坏性操作。当前安装的 Session Secret 保持不变，已有登录会话可能需要重新登录。

## 6. 升级与回滚

从当前源码构建新镜像并升级：

```bash
./scripts/install/upgrade.sh
```

升级前自动创建 `pre-upgrade-*` 备份。升级脚本保存上一镜像标签；代码镜像回滚：

```bash
./scripts/install/rollback.sh
```

代码回滚不会自动 downgrade 数据库。若新版本数据库不向后兼容，先运行 `restore-check`，再用明确的备份执行 `restore.sh --confirm`。

## 7. 卸载

删除容器和网络、保留数据卷与备份：

```bash
./scripts/install/uninstall.sh
```

永久删除当前安装数据卷和安装配置，需要二次确认：

```bash
./scripts/install/uninstall.sh --purge-data --confirm
```

即使 purge，镜像和 `.product-factory/backups/` 仍保留。删除备份是单独的敏感数据清理任务，本脚本不会代删。

## 8. 干净环境验收清单

- 镜像从源码和 lockfile 构建成功。
- PostgreSQL 健康，Alembic 为 `20260824_0011 (head)`。
- 首次账户注册、退出、重新登录成功；未登录保护接口返回 401。
- 第一个账户项目列表为空；第二个账户登录后也为空，且不能读取第一个账户后续创建的项目。
- 大模型和搜索 API 为空且不含历史默认。
- API 与 PostgreSQL没有宿主机公开端口；Web 只绑定用户指定地址。
- SSE 端点可连接，断线恢复基础设施正常；不运行真实 Agent 项目链路。
- 重启后账户、项目空态和持久化卷保持。
- backup、restore-check、upgrade、rollback、stop/start 通过。
- 默认卸载保留数据；purge 只删除当前 Compose project 的命名卷。
- 安装上下文不含 `.runtime`、`.next`、Secret、日志、备份、用户数据或本机绝对路径。

这些条目是容器安装方式的验收清单。当前本机源码环境可用不等于 Compose 已验收；首次公开发布时必须如实标注这项证据边界。
