# 种子内测环境验收记录

> 日期：2026-08-23  
> 结论：**通过（本机单用户种子内测边界）**  
> 项目：销售复盘 Agent  
> 状态：`seed_beta / Context v10 / iteration v1`

## Gate 与阶段

- 用户已批准 G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a`。
- 数据库真实状态为 G5 `approved`、项目 `seed_beta`、Context v10。
- G6 数量为 0，尚未打开；本次不是正式发布。

## 真实 URL 与健康检查

| 项目 | 验收结果 |
|---|---|
| Web | `http://127.0.0.1:3200`，真实 production build 页面可访问 |
| API | `http://127.0.0.1:8200`，`/health` 返回 200 |
| PostgreSQL | 连接正常，项目与 Gate 状态可读 |
| Alembic | `20260822_0006 (head)` |
| 运行包 | `.runtime/seed-beta/releases/`，current/previous 可切换 |

该 URL 是本机回环地址，满足 V1 单用户、本机种子内测边界，不是公网地址。若改为跨设备内网访问，必须先配置受信任 HTTPS 入口并使用 production Cookie 策略。

## 安全

- 内测环境固定 `AUTH_ENFORCED=true`，认证配置不完整时拒绝启动。
- 未登录访问受保护 API 真实返回 401 `AUTH_REQUIRED`。
- 邀请码登录返回 200；登录后访问项目 API 返回 200。
- Session 只使用 HttpOnly Cookie，邀请码和 Session Secret 仅保存在权限为 600 的 `.runtime/seed-beta/`，未修改真实 `.env`，未输出到日志或文档。
- Web 已设置 CSP、`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、Referrer Policy 和 Permissions Policy；API 设置防嵌入、MIME 嗅探、Referrer、权限策略及 API `no-store`。
- AG-UI/SSE 真实返回 `text/event-stream`、`x-event-stream-mode: ag-ui-live`，支持 HttpOnly Session 和 `Last-Event-ID`。

## 恢复与回滚

| 演练 | 结果 |
|---|---|
| 数据库备份 | `product-factory-20260823T082840Z.dump`，763101 bytes，SHA-256 `e09496a6f49392a032c5634a28ec7c9e42263ae1e951136d24c617ffa0f65ce6` |
| 独立恢复 | 恢复到固定前缀临时数据库，核对项目、G5、Context v10、Alembic head 均通过 |
| 清理 | 恢复临时数据库已删除，残留数量 0；主库未执行 downgrade |
| 应用回滚 | 从 `20260823T082925Z` 切回 `20260823T082615Z`，回滚后健康检查通过 |

运维入口：`scripts/seed-beta/configure.sh`、`release.sh`、`start.sh`、`health-check.sh`、`backup.sh`、`restore-check.sh`、`rollback.sh`、`stop.sh`。

## 浏览器与自动化验证

- 真实浏览器：`1440×900`、`390×844`、`819×749` 均通过，无水平溢出。
- 首页登录、销售复盘 Agent 工作区、第 9 阶段“种子用户内测”均真实可见。
- `819×749` warning/error 为 0；页面没有 G6 决策入口。
- Web：21/21。
- Python：76/76。
- PostgreSQL：46/46。
- production build：通过。
- 保留 1 条 Starlette/httpx 弃用警告。

## 当前边界与下一步

- 本轮完成的是内测环境验收，不等于真实种子用户任务数据已经达标。
- 仍需邀请真实种子用户，收集任务成功、失败、使用和反馈数据。
- 真实 429、博查费用/账单、来源质量人工评审和模型路由差异仍未验证。
- 证据达标后才生成 BRD 并打开 G6；G6 必须由用户决定，G6 前不得正式发布。
