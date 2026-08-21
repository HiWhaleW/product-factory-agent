# 产品工厂前端高保真 Design QA

> 日期：2026-08-22  
> 浏览器：ego-browser / ego-lite（任务空间 `101`）  
> 范围：`apps/web/**`、前端资产与前端 QA 证据

## 当前结论

- 附件 1 的两项修改已实现：项目标题右侧的“项目阶段 / Context v1 / 数据库实时投影 / Agent 未接入”信息组已删除；Artifact 画布提示改为真实项目阶段和 Context 版本生成的“项目对齐 V1.0”。
- 附件 2 对应的项目工作区字号已整体提高 `2px`；桌面与移动端的显式响应式覆盖均已同步，未改变冻结交互。
- 图片静止态黑框已移除：品牌、用户头像、事件和 Gate 图标默认使用透明边界并裁掉 PNG 外框，只有 hover 或键盘 focus-within 时恢复黑色轮廓；图标内部线条和 Artifact 文档图形不被误裁。
- 真实 ego-lite DOM、布局、字体与交互核验通过；桌面 `1440×900` 和移动 `390×844` 均无页面级滚动，应用控制台错误为 `0`。
- 本轮 post-change 原生截图未取得：`captureScreenshot` helper 不可用，CDP `Page.captureScreenshot` 两次超时，`Page.startScreencast` 未返回帧。因此本轮不能完成同屏截图式视觉比较，最终结论保持 `blocked`，不以 DOM 指标冒充视觉完成。

## Source visual truth

- 功能页确认稿：`docs/evidence/workspace-hifi-approved.png`，`1586×992`。
- 本轮附件 1：`docs/evidence/workspace-annotation-remove-meta-2026-08-22.png`，要求删除顶部信息组并把画布提示改为“项目对齐 V1.0”。
- 本轮附件 2：`docs/evidence/workspace-annotation-font-plus2-2026-08-22.png`，要求项目工作区所有文字整体增加 `2px`。
- 权威交互基线：`产品工厂Agent_Harness表.html`。
- 历史同屏比较：`docs/evidence/d5-frontend-visual-comparison-2026-08-22.html` / `.png`；它早于本轮字号和信息层级修改，不能作为本轮 post-change 截图证据。

## 本轮实际修改

- `workspace-client.tsx`：删除顶部状态信息组及其无用状态计算；继续显示真实项目名称。
- `workspace-client.tsx` → `artifact-dag.tsx`：传递动态画布标题 `${projectStageLabel(project.state)} V${project.context_version}.0`，没有静态伪造阶段。
- `globals.css`：桌面项目标题、阶段、参与者、群聊、事件、Gate、Permission、输入框、Artifact 节点、预览抽屉、按钮和说明文字均增加 `2px`。
- `globals.css`：移动端项目标题、阶段编号与名称、参与者、头像、Gate 标题、输入区、移动切换、画布标题和抽屉标题条同步增加 `2px`；删除已失效的 `.project-meta` 与隐藏画布说明规则。
- `globals.css`：图片外框改为交互态显示；`design-qa.html` 的附件图片也改为默认透明边框、hover/focus 才显示黑框。

## ego-lite 浏览器证据

机器可读记录：`docs/evidence/d5-frontend-ego-qa-2026-08-22.json`。

### 桌面 1440×900

- 页面：`scrollWidth=1440`、`scrollHeight=900`、`body overflow=hidden`。
- 工作区：`x=32, y=62, w=1376, h=838`；双栏 `521.36 / 850.64px`，约 `37.9 / 62.1`。
- 12 阶段保持 `6×2`，两行顶坐标为 `119 / 172`。
- 顶部四项信息文本均不存在；画布标题为“项目对齐 V1.0”。
- 关键计算字号：品牌 `24px`、导航 `16px`、项目标题 `17px`、阶段 `14px`、参与者 `12px`、消息 `13px`、Gate 标题 `18px`、DAG 标题 `18px`、节点标题 `17px`。
- 应用控制台错误：`0`。
- 图片默认计算样式：品牌和事件图标 `clip-path: inset(2px)`，头像外框为透明且 `box-shadow: none`；品牌真实 hover 后变为 `clip-path: inset(0)`，黑框仅在交互态出现。

### 移动 390×844

- 页面：`scrollWidth=390`、`scrollHeight=844`、`body overflow=hidden`；工作区 `x=6, y=58, w=378, h=786`。
- 12 阶段保持 `6×2`，两行顶坐标为 `100 / 147`。
- “群聊 → 产物 → 群聊”真实点击切换通过。
- 关键计算字号：项目标题 `13px`、阶段 `10px`、阶段编号 `9px`、切换按钮 `13px`、计数 `11px`、参与者标题 `14px`、参与者 `10px`、Gate 标题 `16px`、输入与发送按钮 `12px`、DAG 标题 `15px`、预览标题条 `12px`。
- 三个 Artifact 节点均完整位于画布内部；移动 MiniMap 按冻结逻辑隐藏；预览抽屉宽 `374px`，无横向溢出。
- 应用控制台错误：`0`。
- 同名 `design-qa.html` 已用 ego-lite 在 `1440×900` 与 `390×844` 打开：两端均无横向溢出，2 张附件图片损坏数为 `0`，页面明确显示 `final result: blocked`。

## 实际交互测试

- **群聊：通过。** 真实输入“前端字号调整 QA：真实群聊输入与持久化验证。”成功提交、回显并在刷新后存在。
- **Gate：安全分支通过。** 空理由点击“退回修改”显示“退回、暂停或终止必须填写理由。”；项目仍为“项目对齐”，未提交不可逆决定。
- **Artifact 拖动：通过。** ego-lite CDP 真实指针事件将节点移动约 `70×35px`；只改变 React Flow 本地位置，没有修改业务 Graph。
- **Artifact 预览：通过。** 桌面和移动均可打开“项目对齐简报”预览并关闭；内容继续从受控 Artifact API 读取。
- **移动切换：通过。** 群聊和产物面板互斥显示，页面不滚动。
- **图片 hover / focus：通过。** ego-lite 在桌面真实 hover 品牌和可见消息头像：头像变为黑色边框、`2px 2px` 硬阴影，图片由 `inset(2px)` 变为 `inset(0)`；真实聚焦 Gate 输入框后卡片满足 `:focus-within`，Gate 图标也变为 `inset(0)`。控制台错误为 `0`。
- **Permission：未测成功态。** 当前项目没有开放 PermissionRequest，未伪造测试数据。

## 数据与 Agent 真实性

- 当前“D3 双栏交互验收”项目没有 Agent 入群，参与者区明确显示 4 个 Agent 均未入群。
- 项目、消息、Gate、Artifact 与事件来自真实 FastAPI/PostgreSQL 控制面，不是纯前端 `demoProject` 或静态 mock。
- 当前群聊和 Artifact 内容是人工写入或明确标记的 D4 控制面样例，不是 DeepSeek 或真实 Agent 生成，不能作为 Agent 效果验收证据。
- 后端 / Agent Runtime 并线已有独立 DeepSeek、Factory Lead 和隔离 AI PM 冒烟证据；这不等于当前项目群聊已经接入 Agent。

## Required fidelity surfaces

- **Fonts and typography：代码与计算样式已核验；截图比较 blocked。** 本轮所有目标字号均增加 `2px`，未发现 DOM 裁切；缺少 post-change 原生截图，无法完成最终字形、抗锯齿与视觉密度比较。
- **Spacing and layout rhythm：通过。** `38/62`、`6×2`、页面无滚动、移动切换均保持。
- **Colors and tokens：未修改。** 沿用已确认的“纸上工场”色板和状态色。
- **Image quality and icons：通过交互态核验。** Logo 与 UI 图标继续使用已确认资产；PNG 烘焙矩形外框在静止态被安全裁掉，hover/focus 时恢复，不改图标主体。
- **Copy and content：通过。** 不需要用户理解的顶部技术信息已删除；画布标题来自真实业务状态。
- **Responsiveness：通过。** 桌面和移动布局、内部滚动与抽屉宽度均通过 ego-lite DOM/交互核验。

## 未完成与并线问题

- **P1 / 阻塞：** 本轮 post-change 原生截图通道失败，不能按 Design QA 要求把附件与当前实现放入同一视觉比较输入。需要 ego-lite 截图能力恢复后补拍桌面工作区、桌面预览、移动群聊、移动产物和移动预览，再决定是否从 `blocked` 改为 `passed`。
- Artifact Graph API 仍没有负责人 / Agent 标签与 `created_at`，前端没有伪造确认稿里的负责人和时间。
- 当前没有可回收 PermissionRequest；allow/deny 成功态待后端 / Runtime 并线提供真实测试数据。
- 成功 Gate 决定具有不可逆业务语义，本轮只验证必填阻断；完整成功态应使用专用可回收验收项目。

## 测试与构建

- `pnpm lint:web`：通过。
- `pnpm typecheck`：通过。
- `pnpm test:web`：2 个文件、6 项全部通过。
- `pnpm build`：Next.js 16.3.1 Webpack 生产构建通过。

final result: blocked
