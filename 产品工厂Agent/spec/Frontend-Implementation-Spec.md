# 产品工厂 Agent - 前端实施规格

> 版本：v0.2  
> 日期：2026-08-20  
> 状态：已冻结；D3-D4 采用后端优先、简洁可观察前端  
> 适用：D3-D8 前端实现、联调与真实浏览器验收  
> 阅读版：[Frontend-Implementation-Spec.html](./Frontend-Implementation-Spec.html)

## 1. 结论与边界

前端不是后端完成后的展示层，而是产品工厂核心闭环的一部分：用户必须在同一工作区看见 Agent 入群、流式执行、人工闸、权限请求、累计 Artifact DAG、产物版本和恢复状态。

本规格把 [Interaction-Spec.md](./Interaction-Spec.md) 的交互定义拆成可实现组件、事件投影、状态矩阵、响应式规则、每日任务和退出证据。原始 D3 基线曾是明确标记的 mock 渲染壳；截至 2026-08-23，真实 API、模型、React Flow DAG、主/子 Agent 入群、消息间执行过程和浏览器 QA 已完成，当前项目为 `internal_acceptance / Context v9`。本规格仍保留冻结设计与历史验收条件，不用实现状态反向改写原始需求。

### V1 前端必须做到

- 3 个页面：项目列表、新建/继续项目；项目工作区；内部设置。
- 桌面双栏：左侧群聊约 38%，右侧 Artifact DAG 约 62%。
- 移动端可查看、审批、退回、暂停和提交反馈；不要求精细编辑 DAG。
- 所有可见状态均由后端实体与 Event 投影，可刷新和断线恢复。
- 区分产品 Gate 与单次 PermissionRequest，区分 Artifact DAG 与内部 Task 进度。
- 不显示隐藏思维链、密钥原值、完整敏感输入或无关调试日志。

### V1 明确不做

- 前端直连模型、PostgreSQL、文件系统或 Codex CLI。
- 自由拖线的流程编排器、多人实时协作、企业 SSO/RBAC。
- 在浏览器执行代码、保存 API Key 原值、把 Canvas 内存当事实源。
- 复杂动画、3D 画布、500 节点性能承诺或移动端 DAG 精细编辑。

## 2. 页面与注释线框图

### 2.1 `/` 项目列表 / 新建项目

```text
┌──────────────────────────────────────────────────────────────┐
│ Product Factory                               [内部设置]     │
├──────────────────────────────────────────────────────────────┤
│ 把一个真实想法变成可验证、可交付、可追溯的产品              │
│ [描述想法………………………………………] [创建项目]                │
│ 说明：先生成 Project Brief，G0 前不会拉入 AI PM              │
├──────────────────────────────────────────────────────────────┤
│ 项目筛选：[进行中] [等待我] [暂停] [已完成]                  │
│ ┌项目名────阶段────状态────最后活动────下一步────────────┐   │
│ │销售复盘 Agent  MRD     等待 G1   10:24     [继续]      │   │
│ └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

注释：

1. 创建动作带 `client_request_id`，超时后先查询结果，不重复建项目。
2. “等待我”优先展示未决 Gate/Permission，但两者使用不同标签和动作。
3. 空态要解释从一句想法开始会发生什么，不使用空白大卡片。

### 2.2 `/projects/:projectId` 项目工作区

```text
┌ 项目名 / v1.0 ─ 当前阶段 ─ Run 状态 ─ Context v5 ─────────┐
│ [对齐][MRD][PRD][方案][技术][开发][MVP][内验][种测][BRD][发布][反馈] → 下一轮 │
├────────────────────── 38% ┬─────────────────────── 62% ────┤
│ 群聊 / 参与者             │ Artifact DAG  [筛选][定位][缩放]│
│ ┌旁白：AI PM 已入群────┐ │  Brief ─ Evidence ─ MRD ─ G1   │
│ │AI PM：职责与边界……   │ │                    └ Review    │
│ ├工具事件（可折叠）────┤ │                                  │
│ ├Gate / Permission 卡──┤ │   选中节点 → Preview Drawer      │
│ └消息流────────────────┘ │   版本 / 引用 / 下载 / 关联证据  │
│ [@Agent 输入……………………]│                                  │
└──────────────────────────┴──────────────────────────────────┘
```

注释：

1. 顶部阶段栏显示业务阶段；Run 状态只表示一次执行，不得推进业务阶段。
2. 阶段栏横向滚动并自动定位当前项；“分阶段开发”可展开后端→前端子阶段，反馈节点指向下一轮项目对齐。
3. 群聊是指令与事件流；DAG 是可持久化事实，不把 ToolRun 日志伪装成产物。
4. Gate 卡可推进阶段；Permission 卡只能批准一次工具副作用。
5. 选中 DAG 节点打开预览抽屉，URL 只展示 HTTPS、域名、环境和健康状态。

### 2.3 `/settings` 内部设置

```text
┌ 内部设置 ───────────────────────────────────────────────────┐
│ 模型       Provider: DeepSeek  Model/Base URL: 未验证       │
│            [检查配置]  不显示 API Key 原值                  │
│ Builder    Codex CLI Path / 版本 / 工作区根目录 [只读检查]  │
│ 安全       单并发 / 超时 / maxTurns / retry / 预算上限      │
│ 存储       PostgreSQL / Artifact Root 状态（目标契约）       │
│            [保存非密钥配置]                                 │
└──────────────────────────────────────────────────────────────┘
```

注释：密钥只显示“未配置/已配置/失效”，浏览器不接收原值；D1-D2 页面只是规格，D3 后才实现真实检查。

## 3. 组件树与职责

```text
AppShell
├── GlobalHeader
├── ProjectListPage
│   ├── IdeaComposer
│   ├── ProjectFilters
│   └── ProjectList / ProjectRow
├── ProjectWorkspacePage
│   ├── ProjectHeader
│   ├── StageBar
│   ├── WorkspaceSplit
│   │   ├── ChatPanel
│   │   │   ├── ParticipantList
│   │   │   ├── MessageList
│   │   │   │   ├── UserMessage / AgentMessage / Narration
│   │   │   │   ├── ToolEventCard
│   │   │   │   ├── GateCard
│   │   │   │   └── PermissionCard
│   │   │   └── MessageComposer / MentionMenu
│   │   └── ArtifactWorkspace
│   │       ├── ArtifactToolbar
│   │       ├── ArtifactCanvas
│   │       ├── CanvasLegend
│   │       └── PreviewDrawer
│   └── ReconnectBanner / RecoverySummary
└── SettingsPage
    ├── ModelSettings
    ├── BuilderSettings
    ├── SafetyLimits
    └── StorageStatus
```

| 组件 | 输入事实 | 用户动作 | 禁止承担 |
|---|---|---|---|
| `StageBar` | `project.state`、Gate 状态 | 定位阶段产物 | 自行判断合法迁移 |
| `ChatPanel` | Message + Event cursor | 发消息、@Agent | 保存唯一事件历史 |
| `ToolEventCard` | ToolRun 摘要 | 展开证据、取消可取消任务 | 显示密钥/隐藏思维链 |
| `GateCard` | GateRequest + impacted artifacts | 批准/退回/暂停/Kill | 当普通消息提交 |
| `PermissionCard` | PermissionRequest + input hash | allow/deny | 推进产品阶段 |
| `ArtifactCanvas` | Artifact/Version/Edge | 筛选、定位、折叠、选中 | 由拖线写业务依赖 |
| `PreviewDrawer` | 已授权内容与版本 | 切版本、下载、打开 URL | 执行代码/未消毒 HTML |

## 4. Event / AG-UI 到界面状态映射

所有关键事件先持久化，再推送；前端以 `event_id + cursor` 去重。未知事件保留在诊断摘要中，但不得让页面崩溃。

| 事件 | 主要组件 | 投影结果 | 恢复策略 |
|---|---|---|---|
| `message.created/delta/completed` | MessageList | 建立气泡、增量文本、完成态 | 断线后按 cursor 补齐，再以 message id 合并 |
| `agent.joined` | ParticipantList + Narration | 成员出现、旁白、自介入口 | 以成员快照校正重复事件 |
| `task.*` | ToolEventCard / 进度摘要 | ready/running/blocked/failed | 只显示摘要，不暴露内部 Task DAG 全图 |
| `run.*` | ProjectHeader + 卡片 | 运行、等人、恢复、失败 | 以 Run 快照纠正流事件 |
| `permission.*` | PermissionCard | 等待/批准/拒绝/过期 | 查询原 Decision，禁止重复副作用 |
| `tool_run.*` | ToolEventCard | 开始/完成/失败/取消 | 关联 RunStep 和可见证据摘要 |
| `artifact.created/versioned` | ArtifactCanvas | 新节点或新版本角标 | 重新拉取 graph snapshot |
| `gate.opened/decided` | GateCard + StageBar | 固定待审卡、阶段阻断/推进 | 查询不可变 GateDecision |
| `project.state_changed` | StageBar | 当前阶段与可用动作 | 服务端状态为唯一真相源 |
| `feedback.created/iteration_branched` | Canvas | 从 deployment/url 长出反馈分支 | 旧版本保持只读 |

## 5. 状态设计

| 状态 | 全局表现 | 群聊 | DAG / 预览 | 允许动作 |
|---|---|---|---|---|
| 初次/空 | 解释闭环 | Idea composer | Brief 占位说明 | 创建项目 |
| 加载 | 页面骨架 | 消息 skeleton | 节点 skeleton | 取消导航 |
| 排队 | 显示队列原因 | 任务卡排队 | 不伪造 running 节点 | 取消可取消任务 |
| 流式 | Run 指示器 | 文本 delta + 停止 | 已完成节点可操作 | 停止本次 Run |
| 等待用户 | 顶部固定提醒 | Gate/Permission 卡 | 影响节点高亮 | 做对应决定 |
| 部分成功 | 明确完成/失败数 | 保留成功事件 | 成功分支可用、失败分支有原因 | 重试失败子任务 |
| 失败 | 错误码+用户说明 | 保留上下文 | 节点失败但不消失 | 重试/恢复/暂停 |
| 断线 | ReconnectBanner | 暂停 delta | 保持最后快照、标 stale | 自动重连/手动刷新 |
| stale | 标出旧 Context | 不自动合并旧结果 | 旧版本保留 | 评审后重跑 |
| 恢复 | 显示对账摘要 | cursor 续接 | 从后端重建 | 继续合法步骤 |
| 完成 | 阶段/版本摘要 | 最终消息 | 可追溯主干与分支 | 下载/反馈 |

错误页面不得只显示“Something went wrong”；至少提供 `user_message`、`request_id`、是否可重试和安全下一步。

## 6. 响应式与画布策略

### 桌面与移动

| 断点 | 布局 | 关键行为 |
|---|---|---|
| `>= 1200px` | 38/62 双栏 | 两栏同高；预览抽屉覆盖画布右侧，不挤压群聊 |
| `900-1199px` | 42/58 双栏 | 参与者收为头像组；工具卡默认折叠 |
| `< 900px` | 群聊上、DAG 下 | 顶部阶段栏容器内横向滚动；页面本身无横向溢出 |
| `<= 480px` | 单栏任务优先 | Gate 主操作固定底部；DAG 只查看/缩放/定位 |

### DAG 节点规模

| 规模 | V1 策略 | 验收 |
|---:|---|---|
| 25 节点 | 默认全部渲染；自动 fit view | 定位、筛选、预览无明显卡顿 |
| 100 节点 | 按阶段折叠；仅渲染可见细节；Minimap 可关闭 | 常用交互保持流畅，无错点/丢边 |
| 500 节点 | 风险基线，不作 V1 承诺 | 记录内存/交互退化，触发 V2 虚拟化研究 |

节点位置可作为用户偏好保存，但 Artifact/Edge 关系始终来自后端。刷新后位置丢失不能导致事实丢失。

## 7. 可访问性与安全呈现

- 所有核心动作可用键盘完成，焦点顺序与视觉顺序一致；弹层关闭后焦点回到触发点。
- Gate 的危险动作需文字标签、影响说明和二次确认，不只靠红色。
- 状态不只靠颜色，配合图标、文字和 `aria-live`；流式 delta 不逐字播报。
- 支持 200% 放大和 `prefers-reduced-motion`；点击目标至少 44×44 CSS px。
- Markdown 消毒；代码预览只读；URL 限 `https` 并展示真实域名；文件名去路径字符。
- Console 不输出 Context 原文、Prompt、密钥、完整工具输入或用户文档。

## 8. D3-D8 前端实施排期

| 日 | 前端任务 | 联调对象 | 退出证据 |
|---|---|---|---|
| D3 | AppShell、3 路由、Tokens、共享 contract 壳、错误边界 | 健康检查/配置状态 | desktop/mobile 页面壳可导航；lint/type/build 通过 |
| D4 | mock 群聊、阶段栏、基础 DAG、Gate/Permission 卡、Event reducer | Project/Event/Graph/Gate API | API→UI mock 链路；刷新从快照重建；390px 无页面溢出 |
| D5 | 流式消息、Agent 入群、Evidence/MRD 节点、G0/G1 | DeepSeek/AI PM 切片 | 真模型事件在浏览器可见；断线 cursor 续接 |
| D6 | PRD/方案/技术栈预览、版本切换、stale/partial/compaction、G2-G4 | Artifact/Context/Reviewer | G4 前 Builder 操作不可用；旧版本可追溯 |
| D7 | 后端 Builder 工具事件、API/测试节点、权限卡 | Codex CLI Adapter | 后端退出证据可见；前端 Task 未提前 ready |
| D8 | 前端代码/diff/build、MVP、12 阶段栏、全状态、25/100 节点、键盘/200% | 全纵向切片 | Console/Network 无未解释错误；真实截图/Playwright 证据 |

每天必须保留至少一条 API → 群聊/状态 → Artifact DAG 的可见链路，不采用“先完成后端、D8 再补界面”。

## 9. 验收矩阵

| 领域 | 最低用例 | 放行标准 |
|---|---|---|
| 路由 | `/`、workspace、settings 直达/刷新/返回 | 无 404、状态不丢、错误可恢复 |
| 事件 | 顺序、重复、缺失、未知、断线 | 去重；快照校正；未知事件不崩溃 |
| 群聊 | 长中文、英文、文件名、@4 Agent | 不溢出，路由受阶段约束 |
| Gate | approve/changes/pause/kill、重复点击 | 只生成一次决定；旧 Context 被拒绝 |
| Permission | allow/deny/expired、参数变化 | 不推进阶段；input hash 变化后重新审批 |
| DAG | 25/100 节点、阶段筛选、定位、版本 | 无丢边、错节点、主页面横向溢出 |
| 预览 | Markdown、code、URL、下载 | 消毒、只读、域名/版本清晰 |
| 恢复 | 刷新、断线、Run stale、部分成功 | 服务端事实可重建；不重复副作用 |
| 无障碍 | 键盘、200%、减少动效、读屏标签 | 核心路径可完成，无焦点陷阱 |
| 质量 | desktop/mobile、Console、Network | 无未解释错误或重复副作用请求 |

## 10. 兜底与降级

- SSE/AG-UI 暂不可用：切换到带 cursor 的短轮询，只降低实时性，不改变事件/恢复契约。
- React Flow 在 100 节点性能不足：默认折叠非当前阶段、关闭 Minimap、降低非选中节点细节；不删除历史。
- Markdown 预览失败：显示纯文本安全预览和下载，不渲染未消毒 HTML。
- 事件版本不兼容：隔离未知事件，显示“客户端需刷新/升级”，不猜测字段推进状态。
- DeepSeek 未就绪：D3-D4 只能显示醒目标记的 mock 事件；D5 真模型切片不得用 mock 放行。

## 11. D1-D2 前端收口判定

在不进入 D3 的前提下，前端规格仅当以下项目完成才可进入 Spec Freeze Review：

- [x] 页面、双栏结构、核心交互和 Design Tokens 已定义。
- [x] 组件树、事件映射、全状态、响应式和 DAG 规模策略已补齐。
- [x] D3-D8 每日前端任务和退出证据已写入。
- [x] Markdown 与同名 HTML 阅读版已生成。
- [x] 四项 V1 产品边界已于 2026-08-20 获用户明确批准。
- [ ] 真实前端、浏览器行为和性能已实现并验收；这些属于 D3-D8，不得在当前勾选。

因此当前结论是：**前端规格已按 12 阶段循环修订；D3 静态 mock 壳存在，但尚未忠实实现权威双栏交互。真实 API/模型/DAG 联调、交互符合性和最终浏览器验收均未完成。**
