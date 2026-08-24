# 产品工厂 Agent - GitHub 与火山引擎用户测试环境交接

> 日期：2026-08-24  
> 平台对象：产品工厂 Agent，正在准备真实用户测试环境  
> 内部示范项目：销售复盘 Agent，第 9/12 阶段“种子用户内测”，G6 未打开  
> 目标：用已建立的内部可重现基线安全更新 GitHub Draft PR，再核验火山引擎账号、拓扑与费用边界，用户确认后部署受控种子用户测试环境  
> 边界：平台 `user-beta` 部署不需销售复盘 Agent G6；它不等于该示范项目正式发布

## 0. 三个对象必须分开

| 对象 | 性质 | 当前状态 | 与 G6 的关系 |
|---|---|---|---|
| 销售复盘 Agent | 内部示范项目 | `seed_beta / Context v10 / iteration v1` | 其项目 G6 未打开；若正式发布该项目，仍需真实证据和用户批准 |
| 产品工厂 Agent | 平台产品 | `internal_reproducible_baseline_ready / cloud_preflight_pending` | 下一步更新 GitHub，再做火山引擎账号、拓扑与费用预检 |
| 火山引擎 `user-beta` | 给真实用户测试平台的环境 | 待部署/验收 | 不需先批准销售复盘 Agent G6；不等于销售复盘 Agent 正式发布 |

## 1. 当前可信基线

| 对象 | 当前事实 |
|---|---|
| 内部示范项目 | 销售复盘 Agent 为 `seed_beta / Context v10 / iteration v1`；G0–G5 已批准，项目 G6 未打开 |
| 平台产品 | 产品工厂 Agent 内部可重现基线已建立；GitHub 更新与火山引擎 `user-beta` 预检/部署尚未完成；本机用户环境仍保留旧包 |
| 内部环境 | `127.0.0.1:3200/8200`；current / previous 为 `20260824T074916Z` / `20260824T042123Z` |
| 独立用户环境 | `127.0.0.1:3300/8300`；current / previous 仍为 `20260824T042412Z-identity-only` / `20260824T032335Z-settings-only`；未绑定或重验 `074916Z` |
| 用户环境数据 | Alembic `20260823_0010`；Project、Artifact、Run、Gate、Message、用户模型凭据和内部项目均为 0 |
| 自动化 | Web 34/34、Python 94/94（48 skipped）、PostgreSQL 48/48；production build、ESLint、TypeScript、Ruff 通过 |
| 发布完整性 | `074916Z` SHA-256 manifest 启动前后不变；4 份冻结 Prompt 哈希未变 |
| GitHub | 私有仓库 `HiWhaleW/product-factory-agent`；Draft PR #1 仍 open/draft；本次只读核验的 PR head 为 `69eb31d22430522f32c8db6b1151336756f42d01` |

GitHub head 只是 2026-08-24 本次只读快照。任何远端写入前必须用 GitHub Connector 再次核验，不得使用 `gh`、本地 `git push` 或 `force` 更新。

## 2. 上云前的基线状态：内部可重现，本机用户旧包保持独立

内部 `20260824T074916Z` 已从当前工作区生成可重现 standalone 发布包，并显式包含 API、Alembic `20260823_0010`、依赖锁文件和 4 份冻结 Prompt。SHA-256 manifest 在启动核验前后不变，冻结 Prompt 哈希未变，因此内部源码/构建基线已经建立。

独立用户环境仍是以 `20260824T032335Z-settings-only` 为基底、只追加个人信息模块的 `20260824T042412Z-identity-only`。它尚未绑定或重新验收 `074916Z`，既有用户验收不能自动扩展到新包。

因此下一任务必须保持以下边界：

1. 以内部 `074916Z` 作为 GitHub 源码/构建基线；只上传可重现源码、migration、测试、构建配置和同步文档，不上传 `.runtime`、手工混合 `.next` 或不可重现发布产物。
2. GitHub 更新完成后，直接进入火山引擎账号、地域、网络、资源、费用和拓扑预检；付费资源或目标不唯一时停止并请用户决定。
3. 本机独立用户环境保持当前历史组合包；如后续要绑定 `074916Z`，必须单独完成 preflight、健康、安全、空项目隔离、Secret Store 和桌面/移动浏览器 QA。
4. 未完成本机绑定与重验时不得标记本机 `user_baseline_ready`，但这一独立放行边界不阻塞 GitHub 后的云预检或用户确认后的云上部署。

## 3. 阶段 A：GitHub Connector 更新

1. 读取当前工作区与全部 Git 修改；不 reset、不清理、不重新初始化。
2. 对将上传文件做秘密、邀请码、Session Secret、API Key、数据库连接串、本机敏感路径、运行日志、备份和用户数据扫描。
3. 使用 Connector 重新获取 Draft PR #1 的 head SHA；与预期值不同时停止写入并先对账。
4. 只上传可重现源码、migration、测试、构建配置和同步文档；保持 4 份冻结 Agent Prompt 不变。
5. 通过 Connector 创建 blob/tree/commit，用 `force:false` 更新 `codex/initial-import`。
6. 更新 Draft PR 的真实测试结果、内部可重现基线、本机用户旧包未变和火山引擎待预检状态；保持 Draft，不 merge。
7. 写入后再读取远端 ref/commit/PR，确认 head、文件数和 PR 状态。

## 4. 阶段 B：火山引擎用户测试环境

### 4.1 先做架构预检，不默认“整个项目进 veFaaS”

- 项目冻结规格明确：带本地终端、本地工作区和 Codex CLI 能力的 Builder 不得直接暴露在公开 veFaaS 函数中。
- 先检查 Web、API、SSE/长连接、长任务、PostgreSQL、Artifact/Workspace、用户 Secret Store 和 Builder 的真实运行需求，再决定火山引擎拓扑。
- veFaaS 可作为应用/函数候选，但是否承载 Web/API，以及 Builder 是否留在受控主机，必须用官方文档、实际账号资源和真实冒烟确认，不得凭推测定案。

本机 `vefaas` CLI 为 `0.3.1`，满足 Skill 要求的 `>=0.2.7`；但更新检查本次因网络未完成，下一任务执行云操作前必须重试。

### 4.2 云上用户测试环境必须独立

| 对象 | 要求 |
|---|---|
| 环境名称 | 明确标识为 `user-beta`，不冒充 production |
| 数据库 | 新建独立 PostgreSQL 16 库，从 migration 到 `20260823_0010`；不复制内部项目 |
| Artifact / Workspace | 使用独立持久化存储；路径逃逸与 owner 隔离保持 fail closed |
| 用户 Secret Store | 云环境独立密钥存储；Key 原文不进 GitHub、数据库、日志或构建产物 |
| 认证 | `AUTH_ENFORCED=true`；云上新建 Session Secret 和邀请哈希；HTTPS Cookie 使用 Secure/HttpOnly/SameSite |
| 模型 | 普通用户默认无凭据；由用户自己配置 OpenAI-compatible HTTPS API，无配置时 fail closed |
| 日志 | 不记录邀请码、Session Secret、API Key、隐藏思维链或完整用户文档 |
| 数据初始态 | Project、Artifact、Run、Gate、Message、用户模型凭据和内部项目均为 0 |

本地邀请码、Session Secret、API Key、数据库密码和用户 Secret Store 不得复制到云上；必须在目标环境重新生成并只通过受控秘密渠道配置。

### 4.3 固定执行顺序

```text
内部可重现源码/构建基线（已完成）
  → GitHub Connector 安全更新并反向核验
  → 火山引擎账号/地域/网络/资源/费用预检
  → 确认拓扑、构建命令、启动命令、端口与健康路由
  → 新建云上用户测试数据库和持久化存储
  → 运行 migration 到 20260823_0010
  → 配置云上独立秘密与强制认证
  → 部署 Web/API/Runtime 的已批准拓扑
  → 健康、安全、SSE、隔离、Secret Store、备份/恢复与回滚验收
  → 桌面/移动真实浏览器验收
  → 用户确认后才邀请真实种子用户
```

本机独立用户环境是否绑定 `074916Z` 是另一条受控放行线：未经新的验收不得宣称它已更新，但它不是火山引擎 `user-beta` 的前置 Gate。

## 5. 云上用户测试验收清单

- 公网 HTTPS URL 可访问，Web/API 健康检查通过。
- 未登录受保护 API 返回 401；邀请码登录后进入首页；Session 过期后项目记录仍归属同一用户。
- 用户数据库初始项目为 0，且不存在销售复盘 Agent、内部 fixture 或内部凭据。
- AG-UI/SSE 是主通道；cursor/`Last-Event-ID`、心跳、断线降级和恢复后停止轮询通过。
- API 设置四项默认为空，删除按钮禁用；真实添加/删除后数据库仅有脱敏元数据，秘密存储无残留。
- “个人信息”只显示名称、账号身份、登录状态和退出登录。
- 项目创建、Agent 真实任务、Artifact、Reviewer、Gate、回收箱和恢复跑通；不使用 mock 冒充。
- 用户 A/B 资源隔离、路径逃逸、敏感信息脱敏和 fail-closed 通过。
- 数据库、Artifact 和秘密存储备份/恢复通过；已验收前版可回滚，回滚不破坏用户数据。
- `1440×900`、`390×844` 和用户关键流程真实浏览器 QA 通过，Console/Network 无未解释错误。
- 保存“用户测试部署记录”，包含 Git commit、云资源 ID、版本、URL、migration、健康、日志位置、回滚点和未验证项；记录不包含密钥原文。

只有上述验收通过，才能称“火山引擎平台用户测试环境就绪”。这一部署不需销售复盘 Agent G6，也不等于该示范项目正式发布。

## 6. 必须停止并请用户决定的情况

- GitHub 远端 head 与写入前预期不一致。
- `074916Z` 在独立用户环境绑定或重新验收时无法重现预期行为。
- 需要新增付费云资源、公网网关、域名、证书、VPC 或存储，但账号中没有唯一明确的目标。
- 目标拓扑要把本地 Codex CLI/工作区能力暴露到公开函数。
- 需要复制本地邀请码、Session Secret、API Key、用户 Secret Store 或内部项目数据。
- 部署引入了尚未由用户确认的页面/产品行为变化。

## 7. 权威参考

- [火山引擎函数服务：什么是函数服务](https://www.volcengine.com/docs/6662/97169)（官方文档，更新时间 2026-07-31）
- [火山引擎函数部署快速入门](https://www.volcengine.com/docs/6662/98457)（官方文档，更新时间 2026-07-31）
- [技术适配声明](../产品工厂Agent/spec/Technical-Adaptation.html)
- [验收测试计划](../产品工厂Agent/spec/Acceptance-Test-Plan.html)

## 8. 当前尚未完成

- GitHub 本轮更新尚未写入。
- 独立用户环境尚未绑定或重新验收 `20260824T074916Z`；当前状态不是 `user_baseline_ready`。
- 火山引擎账号、地域、网关、网络、数据库、持久化存储、域名/证书和费用边界尚未核验。
- 云上部署、migration、健康、安全、隔离、恢复/回滚和真实浏览器 QA 尚未执行。
- 产品工厂平台的真实用户任务与反馈数据仍未开始收集。
- 销售复盘 Agent 的真实种子内测证据、BRD、G6 和该项目正式发布仍未完成；这些不阻塞平台 `user-beta` 部署。
