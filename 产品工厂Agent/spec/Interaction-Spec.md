# 产品工厂 Agent - 交互规格

> 版本：v0.2  
> 权威视觉源：[../../产品工厂Agent_Harness表.html](../../产品工厂Agent_Harness表.html)  
> 生命周期投影：[../产品工厂Agent_Harness流程与能力注册表.html](../产品工厂Agent_Harness流程与能力注册表.html)；只负责同步 12 阶段/Gate，不得改变视觉和交互范式  
> 适用：V1 单用户桌面 Web，移动 Web 可查看和审批

## 1. 交互原则

当前 D3 Web 页面不是本规格的实现：它由静态 `demoProject` 驱动，只显示项目事件列表和线性节点，尚无真实群聊输入、完整参与者区、预览抽屉、React Flow 或 API/Event 投影。该页面只能称为 mock 可观察壳，不能反向修改本规格或充当交互符合性证据。

1. **对话管指令，画布管事实**：群聊展示任务、人员、工具事件和审批；DAG 展示可持久化产物及依赖。
2. **只有一个持续窗口**：用户始终留在同一项目群聊；新 Agent 以入群事件加入，不开平行聊天页。
3. **累计 DAG，不覆盖历史**：阶段切换只改变视口和高亮，不清空旧节点。
4. **工具透明，思维链不透出**：展示调用目的、工具、状态、耗时、成本和结果摘要；不展示模型隐藏推理。
5. **人工闸是一等状态**：等待审批时必须明确展示已完成内容、影响、选项、可逆性和阻塞的下一步。

## 2. 信息架构

### V1 页面

| 路由 | 页面 | 职责 |
|---|---|---|
| `/` | 项目列表/新建项目 | 创建、继续、查看暂停/已完成项目 |
| `/projects/:projectId` | 产品工厂工作区 | 群聊、阶段、DAG、产物、人工闸和反馈 |
| `/settings` | 内部设置 | 模型配置键名、Codex CLI 路径、工作区根目录、安全限制 |

### 工作区布局

```text
顶部：项目名 / 版本 / 当前阶段 / 运行状态
阶段栏：12 个本轮用户可见阶段；横向滚动，当前阶段自动定位
左侧 38%：项目群聊 + 参与者 + 工具事件 + 人工闸 + 输入框
右侧 62%：累计产物 DAG + 缩放/定位 + 产物预览抽屉
```

- 桌面端两栏对齐，左右高度一致。
- 小于 `900px` 时改为群聊在上、DAG 在下。
- 移动端必须能完成查看产物、退回、批准、暂停和提交反馈；不要求移动端精细编辑 DAG。
- 阶段栏顺序固定为：项目对齐 → MRD → PRD → 方案确认 → 技术栈确认 → 分阶段开发 → MVP → 内部验收 → 种子用户内测 → BRD/商业模式确认 → 发布/交接 → 数据与反馈。
- “分阶段开发”展开后显示后端、前端两个内部子阶段；后端退出证据未满足时前端 Task 不得进入 `ready`。数据与反馈形成新迭代分支后，视图回到下一轮项目对齐，但保留上一轮整条 DAG。

## 3. 群聊交互

### 消息类型

```typescript
type MessagePart =
  | { type: 'user_text'; text: string }
  | { type: 'agent_text'; agentId: CoreAgentId; text: string }
  | { type: 'narration'; event: 'agent_joined' | 'agent_left' | 'stage_changed'; text: string }
  | { type: 'tool_event'; runId: string; capabilityId: string; status: ToolRunStatus; summary: string }
  | { type: 'artifact_ref'; artifactId: string; version: number }
  | { type: 'gate_request'; gateId: GateId; options: GateOption[] }
  | { type: 'gate_decision'; gateId: GateId; decision: GateDecision };
```

### 新 Agent 入群

1. 主 Agent 计算是否需要独立 Agent，而不是只调用 Skill。
2. 群聊插入旁白：`主 Agent 将 AI PM 拉入了项目群聊`。
3. 主 Agent 发布交接摘要：Context Pack 版本、必读产物、任务和禁止事项。
4. 新 Agent 必须自我介绍：我是谁、负责什么、解决哪些问题、不承担什么、如何 `@`。
5. 群成员栏新增 Agent，点击成员将 `@AgentName` 填入输入框。

### `@Agent` 路由

| 情况 | 行为 |
|---|---|
| Agent 当前在群 | 该 Agent 获得用户消息 + 当前 Context Pack，回复并产生事件 |
| Agent 不在群，但当前阶段允许 | 主 Agent 说明影响，创建 Context Pack，拉入后路由 |
| Agent 不在群且越阶段 | 主 Agent 不直接拉入；说明当前尚缺少的上游证据或审批 |
| `@Skill` / `@工具` | 转给主 Agent 做权限和阶段检查，不允许用户绕过 Harness |

### 工具事件

必须显示：调用人、能力 ID、工具名、开始/完成/失败、耗时、可见成本、结果摘要和关联节点。

不显示：隐藏思维链、密钥、完整敏感原文、无关调试日志。

## 4. 产物 DAG

### 节点类型

```typescript
type ArtifactKind =
  | 'brief'
  | 'evidence'
  | 'markdown'
  | 'design'
  | 'code'
  | 'test_report'
  | 'gate_decision'
  | 'deployment'
  | 'url'
  | 'feedback'
  | 'iteration';

interface ArtifactNodeData {
  artifactId: string;
  projectId: string;
  title: string;
  kind: ArtifactKind;
  status: 'draft' | 'waiting_review' | 'approved' | 'running' | 'failed' | 'superseded';
  version: number;
  stage: ProjectStage;
  contextVersion: number;
  summary: string;
  downloadable: boolean;
  previewType: 'markdown' | 'code' | 'link' | 'structured';
}
```

### 图布局

- 从左向右延伸，每个用户阶段是一个可折叠子图。
- 阶段核心产物形成主干；证据、审核、测试和反馈作为分支。
- 节点之间的边表示依赖，不表示时间顺序的装饰线。
- 当前阶段高亮，历史阶段降权但仍可点击。
- 上线反馈必须从对应 `deployment/url` 节点长出，并建立新迭代分支；不改写旧节点。
- 用户不手动连接工程算子；节点和边由后端事件创建，用户只做移动、折叠、筛选、查看和评论。

### 节点操作

| 节点 | 点击行为 |
|---|---|
| Markdown / 证据 / 报告 | 右侧抽屉渲染 Markdown，支持版本和下载 |
| Code | 语法高亮、文件路径、diff、下载或在工作区打开 |
| URL | 展示环境、版本、健康状态和“打开”按钮 |
| Gate | 展示审批人、选项、时间、原因和关联产物 |
| Feedback | 展示反馈原文、分类、严重度、版本、日志和迭代分支 |

## 5. 人工闸组件

```typescript
interface GatePanelProps {
  gate: GateRequest;
  impactedArtifacts: ArtifactSummary[];
  onApprove(comment?: string): Promise<void>;
  onRequestChanges(comment: string): Promise<void>;
  onPause(reason: string): Promise<void>;
}
```

- `Approve` 不等于发送普通群聊；必须生成不可变的 GateDecision 事件。
- 退回必须填写理由，并创建新产物版本；不覆盖被退回版本。
- 风险项未触发时可显示“未触发及检查依据”，但不得伪造 GateDecision。
- G0-G6 均为产品阶段必审；风险升级显示在最近 Gate 中。全局规则回写使用独立 Governance Review，不再占用产品 Gate 编号。

## 6. 关键状态矩阵

| 模块 | 空 | 载入 | 运行 | 等待人 | 部分成功 | 失败 | 恢复 |
|---|---|---|---|---|---|---|---|
| 群聊 | 显示新建项目输入 | 骨架 | 流式消息/工具事件 | 固定 GatePanel | 保留已完成事件 | 错误摘要+重试 | 按 event cursor 继续 |
| DAG | 显示 Brief 入口 | 节点占位 | 节点运行状态 | 闸节点高亮 | 成功/失败分支 | 节点红色+原因 | 从后端全量重建图 |
| 产物预览 | 选节点提示 | skeleton | 不适用 | 审批操作 | 标记不完整部分 | 保留标题+重试 | 用 artifact version 重拉 |

## 7. Design Tokens

从已确认 HTML 继承，不重新定调：

```css
:root {
  --page: #f4f6f5;
  --surface: #ffffff;
  --surface-2: #eef2f0;
  --text: #17201d;
  --muted: #596661;
  --line: #cbd4d0;
  --agent: #1f65a6;
  --human: #9a5b00;
  --role: #6550a0;
  --tool: #13705b;
  --harness: #a63838;
  --radius-control: 4px;
  --radius-panel: 6px;
  --space-unit: 4px;
}
```

- 字体：`Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif`。
- 所有字重限制为 400/500/700；字距为 0。
- 不使用装饰渐变、悬浮页面卡片或超大英雄标题。
