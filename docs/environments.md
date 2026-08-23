# 产品工厂 Agent - 双环境运行说明

> 同步日期：2026-08-23  
> 状态：内部验证环境与独立用户环境均已建立并通过本机验收  
> 内部发布包：`20260823T155102Z`；用户环境发布包：`20260823T155102Z`（用户已确认内部验收并完成同步）

## 1. 两套环境是什么

| 项目 | 内部验证环境 | 独立用户环境 |
|---|---|---|
| 用途 | 在真实“销售复盘 Agent”上验证完整开发流程 | 给真实种子用户登录并创建自己的项目 |
| Web | `http://127.0.0.1:3200` | `http://127.0.0.1:3300` |
| API | `http://127.0.0.1:8200` | `http://127.0.0.1:8300` |
| 数据 | 保留销售复盘 Agent、内部验收项目与证据 | 独立数据库 `product_factory_user_beta`；初始项目数为 0 |
| 运行目录 | `.runtime/seed-beta/` | `.runtime/user-beta/` |
| Artifact / Workspace | 内部环境专用 | 用户环境专用 |
| Session Secret / 邀请码 | 内部环境专用 | 用户环境专用 |
| 用户 API Key | `.runtime/seed-beta/secrets/`，支持用户配置 OpenAI-compatible 接口；仅管理员可回退到本地测试 Key | `.runtime/user-beta/secrets/`，普通用户必须配置自己的 Key 与接口 |
| 当前角色 | 内部管理员 | 真实种子用户 |

两套环境可以使用同一个内部验收通过的 production 发布包，但绝不能共享数据库、Artifact、Workspace、日志、Session Secret 或邀请码。

## 2. 用户和项目归属

- `users` 是真实用户真相源，`user_invites` 负责邀请码与用户绑定；邀请码只保存哈希。
- HttpOnly Session 绑定数据库用户，项目创建时由后端写入当前用户归属。
- 项目列表只返回当前用户的项目。
- 项目、产物、任务、Run、Gate、Permission 都由后端检查项目归属。
- 跨用户读取返回 404；前端提交其他 owner ID 不会改变归属。
- 用户环境首次登录时首页必须为空；不能出现销售复盘 Agent 或内部 fixture。
- 用户 Key 原文不进入 PostgreSQL、页面回包、日志、Context 或 Artifact；数据库只保存 SecretRef、指纹、脱敏尾号以及接口名称/Base URL/模型名。
- Runtime 优先读取当前项目 owner 的 Key；普通用户未配置或受控文件缺失时拒绝执行，不能静默使用内部 DeepSeek Key。

## 3. 正确发布顺序

```text
当前工作区实现
  → 内部环境迁移、测试、production build、健康与浏览器验收
  → 生成内部 current 发布包
  → 用户环境 preflight
  → 用户环境绑定同一已验收发布包
  → 用户环境健康、安全、空项目隔离、恢复验收
  → 邀请真实种子用户
```

不能跳过内部验证直接把工作区代码切到用户环境。用户环境也不能反向成为内部开发或销售复盘数据的真相源。

## 4. 运维命令

### 内部验证环境

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

### 独立用户环境

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

`scripts/user-beta/release.sh` 只能绑定内部环境已经生成的 `current` 发布包。用户环境当前 current 为 `20260823T155102Z`、previous 为 `20260823T095514Z`；`rollback.sh` 已真实完成双向切换与健康检查，最终恢复到新包。未来版本仍必须先通过内部验收再绑定。

## 5. 当前验证

- Web：26/26。
- Python：86/86。
- PostgreSQL：48/48。
- Alembic：`20260823_0010 (head)`。
- ESLint、TypeScript、Ruff、production build：通过。
- 内部环境和用户环境健康检查：通过。
- 双用户项目隔离、用户环境首次空项目、内部项目不泄露：通过。
- 项目软删除的 owner 隔离、项目名确认、活跃 Run 阻断、删除后 404 与审计保留：通过。
- 回收箱按 Session owner 隔离；恢复回到原阶段、重复恢复幂等并写入 `project.restored`；不提供永久删除：通过。
- 本次 `/projects` 浏览器 QA：`1440×900`、`390×844` 项目列表/回收箱往返且无水平溢出；5 个项目均有删除按钮；顶栏无“帮助”；warning/error 为 0。
- 用户数据库备份和临时数据库恢复：通过。
- 用户 Web/API 健康、强制认证、HttpOnly Session 和安全响应头：通过；数据库已迁移到 `0010`。
- 用户 Secret Store 临时 Key 添加、响应脱敏、`0600` 权限、删除无残留：通过。
- 用户环境 `095514Z ↔ 155102Z` 双向回滚：通过，最终为 `155102Z`。
- 本次 API 设置页浏览器 QA：添加按钮可触发并对空 Key 给出明确错误；无用户 Key 时不展示虚假删除动作；`390×844` 无水平溢出，warning/error 为 0。用户已确认内部验收通过。

## 6. 当前边界

- 两套 URL 都是本机回环地址，不是公网域名。
- 公网 HTTPS 和外部可访问部署尚未完成。
- G5 已批准，当前可以开展真实种子用户内测；环境就绪不等于真实任务与反馈数据已经达标。
- 用户已确认本次内部浏览器验收通过，`20260823T155102Z` 已同步到独立用户环境。
- 达到内测退出阈值后才生成 BRD 并打开 G6；G6 只能由用户决定。

详细证据：[独立用户环境验收记录](./evidence/user-environment-acceptance-2026-08-23.html)。
