# 产品工厂前端 Design QA

> 日期：2026-08-23  
> 当前结果：本次内部自动化与浏览器 QA `passed`；用户验收 `accepted`；用户环境 `ready_for_seed_beta`  
> 种子内测入口：`http://127.0.0.1:3200/`  
> 业务验收项目：`销售复盘 Agent`（`seed_beta / Context v10 / iteration v1`）

## 1. 本轮结论

“销售复盘 Agent”已恢复到 Web 使用的同一 PostgreSQL/FastAPI，并完成真实前端投影验收。首页显示该项目；工作区显示真实 Evidence Index v2、MRD v2、Red Team Review v2；MRD 可读取 v2 与历史 v1；历史 G1 以只读卡片展示两项权威 P2 已知问题。

以下第 1–6 节保留 2026-08-22 的历史投影验收快照，当时没有推进 PRD、批准 G2 或启动 Builder。它不是当前状态；当前事实以第 10 节为准：项目已到 `seed_beta / Context v10`，G5 已由用户批准。

本轮修复了两项 QA 中发现的投影错误：

- Artifact 节点角标由项目 Context `V3.0` 改为各产物真实修订版 `v2`；工作区标题仍保留项目阶段与 Context 版本 `PRD V3.0`。
- 工作区 Gate 查询由仅取 `open` 改为取 `all`；已关闭 G0/G1 使用只读历史卡，不出现可再次提交的决定按钮。

## 2. 历史真实性核验（2026-08-22 快照）

| 项目 | 实际结果 |
|---|---|
| 项目 | `销售复盘 Agent`，ID `2a3c38e1-9704-4f83-a096-84cb5a5025e7` |
| 阶段 | `prd / Context v3 / iteration v1` |
| 产物 | MRD v2、Evidence Index v2、Red Team Review v2；后续新增 PRD/Review v1，均来自真实 Artifact Graph |
| 历史版本 | MRD v2/v1 都可读取；版本索引含状态、时间、创建者和内容可用性 |
| G1 | `approved` 的只读历史卡，关联 3 个真实产物版本 |
| G2 | `open`、未决定；ID `fdac9cd1-3cb8-4a98-b87d-18d8ef779e82` |
| 已知问题 | `引用粒度待用户访谈验证`；`Gong 定价和客户规模缺少直接证据` |
| Runtime | Factory Lead、AI PM、Reviewer Membership/Task/Run/Step/ToolRun 可从执行投影读取 |
| Builder | 未入群、未激活、未运行 |
| Session | `/me` 返回 `auth_not_configured`、`auth_enforced=false`；页面明确未启用登录 |

## 3. ego-lite 生产模式验证

浏览器只使用 ego-lite / ego-browser。机器可读证据见 [d5-runtime-projection-ego-qa-2026-08-22.json](./docs/evidence/d5-runtime-projection-ego-qa-2026-08-22.json)。

### 3.1 桌面 1440×900

| 验收项 | 结果 | 证据摘要 |
|---|---|---|
| 首页/统一导航 | 通过 | 首页出现销售复盘项目；设置页可达 |
| 30/70 双栏与 12 阶段 | 通过 | 工作区为单屏双栏；12 阶段保持 6×2 |
| 群聊/参与者 | 通过 | Factory Lead、AI PM、Reviewer 已入群；Builder 未入群；AI PM hover 命中 |
| Artifact 节点 | 通过 | 三个节点均显示真实 `v2` |
| 版本预览 | 通过 | MRD 下拉显示 `v2 · 最新` 与 `v1 · 历史`；切换后正文与引用/修改/下载标签同步到 v1 |
| G1 历史卡 | 通过 | 只读 `approved`；两项 P2 可见；无决定按钮 |
| Artifact 拖动 | 通过 | CDP 指针把 MRD transform 从 `(305,110)` 移到 `(435,173)`；Graph API 仍返回同一 MRD v2 |
| 设置/Session | 通过 | “未启用登录”“auth_not_configured”“尚未启用强制认证”可见 |
| 404 | 通过 | 不存在项目显示“项目不存在”和返回项目列表入口 |
| Console/应用错误 | 通过 | 生产应用错误 0；忽略 ego-lite 自带扩展的 info 日志 |

### 3.2 移动 390×844

| 验收项 | 结果 | 证据摘要 |
|---|---|---|
| 同屏切换 | 通过 | 默认群聊；点击产物后 chat `display:none`、DAG `display:flex` |
| Artifact 节点 | 通过 | MRD、Evidence Index、Red Team Review 均显示 v2 |
| 版本预览 | 通过 | MRD 显示 v2/v1 两个真实版本选项 |
| G1 已知问题 | 通过 | 两项 P2 均在移动 DOM 中 |
| 页面错误 | 通过 | 应用错误 0 |

## 4. 自动化验证

- Web ESLint：通过。
- Web TypeScript：通过。
- Web Vitest：3 个文件、19 项通过。
- Next.js 16.3.1 production build：通过。
- Python Ruff：通过。
- Python 测试：68 项通过。
- PostgreSQL 集成/并发/恢复测试：46 项通过。
- Alembic：`20260822_0006 (head)`。
- 保留 1 条 Starlette TestClient/httpx 弃用警告。

## 5. 当时未安全测试与未完成项（历史快照）

- 专用可回收 PermissionRequest/Gate fixture `c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001` 数据已存在，但应用桌面/移动联合浏览器验收尚未完成；不得对真实业务项目做破坏性验收。
- 真实 G2 已打开，必须等待用户人工决定；本轮文档更新没有批准或退回 G2。
- Builder、MVP、内测、G5/G6、发布和线上地址未完成。
- 2500ms cursor 短轮询仍是 AG-UI/SSE 未完成前的降级实现；工作区不再显示该标签不代表传输层完成。
- Session 签发、`/me`、logout 契约已存在，但当前未配置邀请认证，且业务请求强制认证仍为 `false`。
- DeepSeek 配置名 `deepseek-chat` 与运行返回 `deepseek-v4-flash` 的差异仍待确认。
- 真实 429、博查账单/费用和来源质量人工评审未验证。

## 6. 视觉证据边界

本轮 ego-lite 的 `Page.captureScreenshot` 在复用任务空间和新隔离任务空间均超时；因此没有生成新的桌面/移动 PNG，也没有把历史截图改名冒充本轮证据。DOM、语义树、CDP 指针交互、真实端点和 Console/应用事件均已核验。

历史已确认视觉证据仍以 `docs/evidence/d5-*-production-*-2026-08-22.png` 为准；本轮新增机器证据只记录真实运行态投影与交互结果。

## 7. 最终状态

`passed`

当前确认稿与本轮真实投影范围通过。该结论不等于视觉永久冻结、真实内测数据达标或正式发布完成。

## 8. 2026-08-23 阶段导航与群聊交互历史回归

本节保留当时 `internal_acceptance / Context v9` 页面记录；当前事实以第 10 节为准。

| 验收项 | 结果 | 真实浏览器证据 |
|---|---|---|
| 已完成阶段联动 | 通过 | 桌面点击 PRD 后，群聊阶段标记顶部 `284.13px`、滚动容器顶部 `276px`；画布同步定位 PRD 产物 |
| 移动阶段联动 | 通过 | `390×844` 点击 MRD 后自动切换产物画布；切回群聊并等待 3.5 秒后，MRD 标记顶部 `293.96px`、容器顶部 `286px`，定位未被轮询冲掉 |
| 子 Agent 趣味入群 | 通过 | 仅依据真实 `agent.joined`，先展示 Factory Lead 创建群聊或邀请子 Agent 入群，再由 Agent 自我介绍功能、职责和可 @ 场景 |
| 对话间处理过程 | 通过 | 143 条 Run、工具、任务、Context 与产物事件按真实消息、Run 和阶段边界拆成 38 个折叠组；用户消息 → 处理过程 → Agent 回复的顺序可见 |
| 小白文案与排版 | 通过 | 不再直接显示 `context.pack_created`、Run ID 等技术字段；显示“准备资料”“调用网络搜索工具：博查”等通俗步骤，步骤改为时间 + 两行内容，文字无重叠 |
| 缩放控件动效 | 通过 | 控件容器 `box-shadow: none`、`transition: 0s`；放大/缩小按钮 `transition: none` |
| 当时 Gate | 未决定 | 当时 G5 `3fb3ef9f-91c9-433f-a56b-10521ec13b4a` 保持 open；未开始种子内测 |

回归验证：Web ESLint、TypeScript、Vitest `21/21`、Next.js 16.3.1 production build 全部通过；应用内浏览器覆盖用户标注的 `819×749` 视口，并完成消息顺序、展开步骤和无文字重叠检查。

## 9. 2026-08-23 AG-UI/SSE 与认证强制执行回归

| 验收项 | 结果 | 真实证据 |
|---|---|---|
| 未登录 Gate | 通过 | 临时开启 `AUTH_ENFORCED=true` 后，首页只显示邀请码登录；无 Session 访问 `/api/v1/projects` 真实返回 401 |
| HttpOnly Session | 通过 | 邀请码登录后受保护首页和销售复盘工作区可访问；前端代码不读取令牌或密钥 |
| AG-UI/SSE 主通道 | 通过 | 工作区建立 `/events/stream?cursor=160` 长连接，后端返回 200；SSE `id` 使用持久化事件 sequence |
| 断线降级 | 通过 | 独立测试 API 停止后页面显示“事件连接暂时中断”，并按 2500ms cursor 轮询保留快照 |
| 自动恢复 | 通过 | API 恢复后重新建立 SSE，降级提示消失，轮询停止；当时 G5 仍为 open |
| `819×749` | 通过 | 无水平溢出，当前阶段为内部验收，G5 决策卡保持开放；浏览器 warning/error 为 0 |

当时自动化基线：Web `21/21`、Python `75/75`、PostgreSQL `46/46`、Alembic `20260822_0006 (head)`、production build 通过。保留 1 条 Starlette/httpx 弃用警告。

## 10. 2026-08-23 种子内测环境浏览器验收

| 验收项 | 结果 | 真实证据 |
|---|---|---|
| 强制登录 | 通过 | `127.0.0.1:3200` 首屏只显示邀请码登录；登录后项目列表和工作区可访问 |
| 当前阶段 | 通过 | 首页和销售复盘 Agent 工作区显示第 9 阶段“种子用户内测”、Context v10；未出现 G6 决策入口 |
| 桌面 `1440×900` | 通过 | 30/70 双栏与产物画布可见；水平溢出为 0 |
| 移动 `390×844` | 通过 | 群聊/产物同屏切换保留；水平溢出为 0 |
| 标注视口 `819×749` | 通过 | 当前阶段、群聊和输入区可用；水平溢出为 0；warning/error 为 0 |
| SSE | 通过 | 真实 URL 返回 `text/event-stream` 与 `ag-ui-live`，连接持续打开 |

当时自动化基线：Web `22/22`、Python `76/76`、PostgreSQL `46/46`、Alembic `20260822_0006 (head)`、production build 通过。该轮内部环境的健康、安全、恢复和回滚证据见 `docs/evidence/seed-beta-environment-acceptance-2026-08-23.html`；当前全局基线以第 12 节为准。

## 11. 2026-08-23 登录页与首次引导回归

| 验收项 | 结果 | 真实浏览器证据 |
|---|---|---|
| 未登录首页 | 通过 | 不渲染首次引导 Dialog 或遮罩；邀请码登录卡片位于页面中部 |
| 首次登录 | 通过 | 使用真实邀请码登录后自动显示首次引导；引导卡片位于视口正中 |
| 背景虚化 | 通过 | 全屏遮罩为 `position: fixed`，`backdrop-filter: blur(8px)`，覆盖主页内容 |
| 仅自动一次 | 通过 | 首次显示后重新打开同一 Origin，首次引导不再自动出现 |
| 当时手动重开 | 历史通过 | 当时“帮助 → 重新打开首次引导”可再次打开；该无效入口已按用户要求在当前版本移除 |
| 桌面 `1440×900` | 通过 | 登录卡片水平居中，无首次引导，无水平溢出 |
| 移动 `390×844` | 通过 | 登录卡片和首次引导均居中，无水平溢出 |
| Console | 通过 | warning/error 为 0 |

本轮 Web ESLint、TypeScript、Vitest `22/22` 和 Next.js 16.3.1 production build 均通过。

## 12. 2026-08-23 真实用户与独立环境回归

| 验收项 | 结果 | 真实证据 |
|---|---|---|
| 真实身份 | 通过 | Session 绑定数据库用户；`/me` 返回真实用户 ID、显示名和角色 |
| 项目归属 | 通过 | A 创建项目后 B 的列表仍为空；B 访问 A 的项目和 Graph 返回 404 |
| 后端强制隔离 | 通过 | 项目、产物、任务、Run、Gate、Permission 均按当前 Session 用户校验，前端伪造 owner 无效 |
| 内部环境 | 通过 | `127.0.0.1:3200/8200` 保留销售复盘 Agent；浏览器显示“内部管理员”，warning/error 为 0 |
| 独立用户环境 | 通过 | `127.0.0.1:3300/8300` 使用独立数据库；未登录 API 返回 401，首次登录项目 JSON 为 `[]`，内部项目数为 0 |
| 数据恢复 | 通过 | 用户数据库备份恢复到临时数据库后，项目 0、用户 1、内部项目 0、Alembic `20260823_0007` |
| 首版回滚保护 | 通过 | 当前无 previous 版本，回滚脚本以退出码 1 安全拒绝，用户 Web/API 保持运行 |

最新自动化基线：Web `22/22`、Python `77/77`、PostgreSQL `47/47`、Alembic `20260823_0007 (head)`、production build 通过。独立用户环境登录页已做真实浏览器检查；公网部署和跨版本应用回滚尚未完成。

## 13. 2026-08-23 用户 API 设置与首次引导变更

| 验收项 | 状态 | 证据/边界 |
|---|---|---|
| DeepSeek API 设置 | 待用户浏览器验收 | 设置页已提供添加、替换、删除和脱敏状态；Key 输入框不回显原文 |
| 5 步首次引导 | 待用户浏览器验收 | 新增“先连接你的 AI”和“去设置 API Key”；仍只在首次登录首页自动显示 |
| 后端 Key 隔离 | 通过 | Key 原文只存权限 `0600` 的用户隔离文件；数据库、响应、校验错误不含原文 |
| Runtime owner 绑定 | 通过 | 当前登录用户/项目 owner 的 Key 优先；普通用户未配置时 fail closed；仅管理员允许本地测试 Key 回退 |
| 双用户 PostgreSQL | 通过 | 两名真实测试用户的 Key、元数据和删除操作互不影响 |
| 内部发布包 | 已部署 | `20260823T112609Z`，健康检查通过，供用户在 `http://localhost:3200` 自行验收 |
| 独立用户环境 | 未同步 | 仍为 `20260823T095514Z`；等待用户确认内部验收通过后再按顺序绑定新发布包 |

最新自动化基线：Web `23/23`、Python `83/83`、PostgreSQL `48/48`、Alembic `20260823_0008 (head)`、production build 通过。由于用户明确选择自行验收，本节没有虚报新的浏览器通过结果。

## 14. 2026-08-23 首页、项目列表、个人信息与通用 API 设置

| 验收项 | 状态 | 证据/边界 |
|---|---|---|
| 顶部导航 | 待用户浏览器验收 | 顺序为“首页 / 项目列表 / 设置”；“项目列表”直接进入 `/projects` |
| 个人信息 | 待用户浏览器验收 | 顶部固定显示“个人信息”，弹层承载用户、角色、用户 ID、运行模式、Session、安全说明和退出登录 |
| 独立首页 | 待用户浏览器验收 | `/` 不再展示项目列表；真实项目与创建入口移入 `/projects` |
| 设置页 | 待用户浏览器验收 | 删除“运行状态”和“用户与会话”，只保留 API Key 添加、替换、删除 |
| 模型接口 | 后端通过 | 支持用户配置公开 HTTPS 的 OpenAI-compatible Base URL 与模型名；Runtime 按项目 owner 使用该配置 |
| 安全 | 后端通过 | Key 仍只进 `0600` Secret Store；拒绝 HTTP、本机和直接内网 IP 地址 |
| 内部发布包 | 已部署 | `20260823T121853Z`，`http://127.0.0.1:3200` 健康检查通过 |
| 独立用户环境 | 未同步 | 仍为 `20260823T095514Z`，等待用户确认内部验收 |

最新自动化基线：Web `23/23`、Python `86/86`、PostgreSQL `48/48`、Alembic `20260823_0009 (head)`、Ruff/ESLint/TypeScript/production build 全部通过。由于用户自行验收，本节不声称浏览器已通过。

## 15. 2026-08-23 项目删除与顶栏精简

| 验收项 | 状态 | 真实证据/边界 |
|---|---|---|
| 项目删除入口 | 通过 | `/projects` 的 5 个真实项目行均显示“删除”；与“继续项目/去处理”组成同一操作组 |
| 删除控制面 | 通过 | 使用 `deleted_at` 软删除；Session owner 校验、项目名确认、活跃 `pending/running` Run 阻断、删除后列表隐藏和受保护入口 404 均由 PostgreSQL 集成测试覆盖 |
| 审计与恢复 | 通过 | Run、Gate、Artifact 和 `project.deleted` 事件保留；不物理删除业务历史 |
| 顶栏真实性 | 通过 | “帮助”、`?` 快捷键、“聚焦项目搜索”和“打开帮助”已全部移除；DOM 中“帮助”数量为 0 |
| 桌面 `1440×900` | 通过 | 实际 viewport 为 `1440×900`；项目列表无水平溢出，删除按钮可见 |
| 移动 `390×844` | 通过 | 实际 viewport 为 `390×844`；项目操作组不溢出，删除按钮可见 |
| Console | 通过 | warning/error 为 0 |
| 发布与隔离 | 通过 | 内部包 `20260823T132019Z`、Alembic `20260823_0010 (head)`；用户环境仍为 `20260823T095514Z` / `0008`，未修改 |

最新自动化基线保持：Web `23/23`、Python `86/86`、PostgreSQL `48/48`、Ruff/ESLint/TypeScript/production build 通过，保留 1 条 Starlette/httpx 弃用警告。浏览器自动化验证已通过，但用户本人尚未确认本次验收通过，因此当前 Gate 状态仍为 `pending_user_acceptance`，不得同步用户环境。

## 16. 2026-08-23 回收箱与恢复闭环

| 验收项 | 状态 | 真实证据/边界 |
|---|---|---|
| 回收箱入口 | 通过 | “真实项目”标题栏固定显示“回收箱”；可在项目列表与回收箱间往返 |
| 用户隔离 | 通过 | 回收箱查询和恢复均以后端 HttpOnly Session owner 为准；跨用户回收箱为空，跨用户恢复返回 404 |
| 恢复动作 | 通过 | 真实 PostgreSQL 测试跑通删除 → 回收箱可见 → 恢复 → 项目列表重新可见；恢复写入 `project.restored` |
| 幂等 | 通过 | 对已恢复项目重复调用恢复接口返回同一项目，不重复写恢复事件 |
| 数据保留 | 通过 | 不提供永久删除；Run、Gate、Artifact、Context 和删除/恢复审计链全部保留 |
| 桌面 `1440×900` | 通过 | 回收箱标题、数量、返回按钮和空状态可见；无水平溢出 |
| 移动 `390×844` | 通过 | 回收箱操作区和空状态完整可见；无水平溢出 |
| Console | 通过 | warning/error 为 0 |
| 发布与隔离 | 通过 | 内部包 `20260823T135555Z` / Alembic `0010`；用户环境仍为 `20260823T095514Z` / `0008`，未修改 |

最新自动化基线保持：Web `23/23`、Python `86/86`、PostgreSQL `48/48`、production build 通过，保留 1 条 Starlette/httpx 弃用警告。当前结果为 `internal_qa_passed / pending_user_acceptance`。

## 17. 2026-08-23 登录落点、普通用户身份与项目操作按钮

| 验收项 | 状态 | 真实证据/边界 |
|---|---|---|
| 登录后落点 | 已实现，待用户手动确认 | 登录成功后执行 `router.replace("/")` 并刷新服务端数据，不再停留在 `/projects` 或 `/settings` 登录页 |
| 普通用户个人信息 | 实现核验通过 | 后端 Session 为 `role=user` 时显示用户昵称、角色“用户”、用户 ID、运行模式“用户工作空间”、会话状态、Session 原因和强制认证状态；不显示“内部管理员/内部验证环境” |
| 桌面项目操作 | 通过 | 真实浏览器计算样式：“去处理”和“继续项目”均为 `88×44px`，`justify-content:center`、`text-align:center` |
| 移动项目操作 | 通过 | `390×844` 下两者均为 `157.5×44px`，文字居中，页面 `scrollWidth=innerWidth=390` |
| 当前回收箱 | 只读核验 | 当前 4 个活跃项目、1 个回收箱项目“D3 PostgreSQL 安装冒烟”；本轮未擅自恢复用户删除状态 |
| Console | 通过 | warning/error 为 0 |
| 发布与隔离 | 通过 | 内部包 `20260823T143242Z` / Alembic `0010`；用户环境仍为 `20260823T095514Z` / `0008`，未修改 |

Web ESLint、TypeScript、Vitest `23/23` 和 Next.js 16.3.1 production build 通过。当前结果保持 `internal_qa_passed / pending_user_acceptance`。

## 18. 2026-08-24 API Key 添加/删除状态与内部服务托管

| 验收项 | 状态 | 真实证据/边界 |
|---|---|---|
| 添加动作 | 通过 | “添加 API Key”不再因空 Key 静默禁用；点击后明确显示“请先粘贴 API Key，再点击添加” |
| 表单校验 | 通过 | 接口名称、HTTPS Base URL、模型名、Key 长度与空白字符均有前端提示；后端仍执行同等或更严格校验 |
| 删除动作 | 通过 | 未保存用户自己的 Key 时显示“尚未保存用户 API Key，无需删除”；只有 `configured=true` 才显示真实删除按钮 |
| 内部回退 | 通过 | 管理员环境 Key 仍只是内部测试回退，不伪装成可由用户删除的用户 Key |
| PostgreSQL 闭环 | 通过 | 48 项在线测试包含双用户 Key 添加、隔离、脱敏响应和删除；未读取、替换或删除管理员真实 Key |
| 浏览器桌面 | 通过 | 新生产包设置页真实打开，空 Key 错误提示可见，warning/error 为 0 |
| 浏览器移动 | 通过 | `390×844` 下 `scrollWidth=clientWidth=390`，添加与空删除状态完整可见，warning/error 为 0 |
| 服务托管 | 通过 | 内部 Web/API 由受控本机监督任务托管；PID 额外校验端口命令标记，陈旧 PID 不再冒充项目服务 |
| 发布与隔离 | 通过 | 内部包 `20260823T155102Z` / Alembic `0010`；用户环境仍为 `20260823T095514Z` / `0008`，未修改 |

最新自动化基线：Web `26/26`、Python `86/86`、PostgreSQL `48/48`、ESLint/TypeScript/Ruff/production build 通过，保留 1 条 Starlette/httpx 弃用警告。当前结果保持 `internal_qa_passed / pending_user_acceptance`。

## 19. 2026-08-24 用户确认与独立用户环境同步

| 验收项 | 状态 | 真实证据/边界 |
|---|---|---|
| 用户内部验收 | 通过 | 用户明确回复“现在内测没问题”，批准按既定顺序同步独立用户环境；不等同于 G6 批准 |
| 数据库迁移 | 通过 | 迁移前项目 0、用户 1、内部项目 0；`0008 → 0009 → 0010` 后保持相同隔离状态 |
| 发布绑定 | 通过 | 内部与用户环境均绑定同一已验收包 `20260823T155102Z`；previous 为 `20260823T095514Z` |
| Secret Store | 通过 | 临时 Key 添加、响应脱敏、`0600` 权限、删除无残留通过；测试 Key 未保留 |
| 恢复 | 通过 | 迁移后备份恢复到隔离临时库，项目 0、用户 1、内部项目 0、Alembic `0010` |
| 跨版本回滚 | 通过 | `155102Z → 095514Z → 155102Z` 两次健康检查通过；最终回到新包 |
| 最终健康与隔离 | 通过 | `3300/8300` 健康、强制认证、HttpOnly Session、安全响应头、首次登录空项目和内部项目不泄露通过 |
| 真实浏览器 | 部分通过 | 未登录首页在桌面和 `390×844` 下渲染正常，无错误覆盖和 console error；登录后的体验留给用户本人最终确认，自动化登录/隔离已通过 |

当前结果：`user_accepted / user_environment_ready / seed_beta`。G6 尚未打开，公网域名、HTTPS、真实种子用户数据和完整第三方模型效果仍未完成。
