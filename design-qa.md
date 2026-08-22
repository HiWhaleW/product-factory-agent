# 产品工厂前端 Design QA

> 日期：2026-08-23  
> 当前结果：`passed_with_visual_capture_gap`  
> 生产入口：`http://127.0.0.1:3100/`  
> 业务验收项目：`销售复盘 Agent`（`prd / Context v3 / iteration v1`）

## 1. 本轮结论

“销售复盘 Agent”已恢复到 Web 使用的同一 PostgreSQL/FastAPI，并完成真实前端投影验收。首页显示该项目；工作区显示真实 Evidence Index v2、MRD v2、Red Team Review v2；MRD 可读取 v2 与历史 v1；历史 G1 以只读卡片展示两项权威 P2 已知问题。

本轮没有推进 PRD、没有打开或批准 G2、没有启动 Builder，也没有提交 Gate、Permission 或群聊消息。

本轮修复了两项 QA 中发现的投影错误：

- Artifact 节点角标由项目 Context `V3.0` 改为各产物真实修订版 `v2`；工作区标题仍保留项目阶段与 Context 版本 `PRD V3.0`。
- 工作区 Gate 查询由仅取 `open` 改为取 `all`；已关闭 G0/G1 使用只读历史卡，不出现可再次提交的决定按钮。

## 2. 真实性核验

| 项目 | 实际结果 |
|---|---|
| 项目 | `销售复盘 Agent`，ID `2a3c38e1-9704-4f83-a096-84cb5a5025e7` |
| 阶段 | `prd / Context v3 / iteration v1` |
| 产物 | MRD v2、Evidence Index v2、Red Team Review v2，均来自真实 Artifact Graph |
| 历史版本 | MRD v2/v1 都可读取；版本索引含状态、时间、创建者和内容可用性 |
| G1 | `approved` 的只读历史卡，关联 3 个真实产物版本 |
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
- Web Vitest：3 个文件、13 项通过。
- Next.js 16.3.1 production build：通过。
- Python Ruff：通过。
- Python单元测试：56 项通过，42 项集成测试按标记跳过。
- PostgreSQL 集成/并发/恢复测试：42 项通过。
- Alembic：`20260822_0006 (head)`。
- 保留 1 条 Starlette TestClient/httpx 弃用警告。

## 5. 未安全测试与未完成项

- 当前没有专用、可回收的开放 PermissionRequest/Gate 联合浏览器样本；未对真实项目执行不可逆决定。
- G2 必须等待用户人工决定；本轮未打开 G2。
- Builder、MVP、内测、G5/G6、发布和线上地址未完成。
- 2500ms cursor 短轮询仍是 AG-UI/SSE 未完成前的降级实现；工作区不再显示该标签不代表传输层完成。
- Session 签发、`/me`、logout 契约已存在，但当前未配置邀请认证，且业务请求强制认证仍为 `false`。
- DeepSeek 配置名 `deepseek-chat` 与运行返回 `deepseek-v4-flash` 的差异仍待确认。
- 真实 429、博查账单/费用和来源质量人工评审未验证。

## 6. 视觉证据边界

本轮 ego-lite 的 `Page.captureScreenshot` 在复用任务空间和新隔离任务空间均超时；因此没有生成新的桌面/移动 PNG，也没有把历史截图改名冒充本轮证据。DOM、语义树、CDP 指针交互、真实端点和 Console/应用事件均已核验。

历史已确认视觉证据仍以 `docs/evidence/d5-*-production-*-2026-08-22.png` 为准；本轮新增机器证据只记录真实运行态投影与交互结果。

## 7. 最终状态

`passed_with_visual_capture_gap`

当前确认稿与本轮真实投影范围通过；新截图生成存在工具缺口。该结论不等于视觉永久冻结、完整 D5 验收、G2 批准或 Builder 可启动。
