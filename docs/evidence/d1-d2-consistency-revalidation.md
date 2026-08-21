# 产品工厂 Agent - D1-D2 一致性复验归档

> 版本：v0.2  
> 复验日期：2026-08-20  
> 结论：**规格一致性通过（PASS）；浏览器/交互符合性未验收**  
> 项目阶段：D1-D2 已完成并冻结；D3 进行中

## 1. 复验目标

确认生命周期 v0.2 修订只改变产品阶段顺序及其 Gate 映射，没有改变既有 Agent 架构、职责、Prompt、技术路线和 Harness 控制原则。本文只归档规格语义一致性；不再把不同页面的历史截图合并为浏览器或交互验收证据。

## 2. 一致性矩阵

| 检查项 | 冻结结论 | 核验来源 | 结果 |
|---|---|---|---|
| 核心 Agent | Factory Lead、AI PM、Builder、Reviewer，共 4 个 | `spec/README.md`、`Capability-Registry.md`、4 份 Prompt | 通过 |
| 用户生命周期 | 12 个本轮阶段；反馈回到下一轮项目对齐，不增加第 13 阶段 | `docs/product-lifecycle.md`、`State-Machine-and-Gates.md`、`Interaction-Spec.md` | 通过 |
| 开发顺序 | 分阶段开发内部固定为后端 → 前端；后端退出证据未满足时前端不得 `ready` | `State-Machine-and-Gates.md`、`Engineering-Schedule.md`、`Acceptance-Test-Plan.md` | 通过 |
| 产品 Gate | G0-G6 七个必审；全局规则回写走独立 Governance Review | `State-Machine-and-Gates.md`、`docs/PRD.md` | 通过 |
| Context Pack | 版本化、最小权限、精确取回；不共享隐藏思维链、整段群聊或密钥原值 | `Context-Schema.md`、`Technical-Adaptation.md` | 通过 |
| 双 DAG | 用户可见 Artifact DAG 与内部 Execution Task DAG 分离 | `docs/architecture.md`、`spec/README.md` | 通过 |
| 控制面分离 | Product Gate ≠ PermissionRequest；Context Pack ≠ Run 上下文压缩 | `Context-Schema.md`、`State-Machine-and-Gates.md`、`Acceptance-Test-Plan.md` | 通过 |
| Agent/Harness 边界 | LangGraph 只负责 Run 循环、暂停和恢复；状态、Gate、权限、预算、幂等由确定性代码执行 | `Technical-Adaptation.md`、`docs/architecture.md` | 通过 |
| 模型与 RAG | V1 仅 DeepSeek；具体接入待真实冒烟；V1 不使用向量 RAG | `Technical-Adaptation.md`、`AGENTS.md` | 通过 |
| 交互范式 | 38/62 双栏：左侧团队群聊，右侧累计产物画布；节点、连线、预览、缩放和反馈分支保留 | 根目录 `产品工厂Agent_Harness表.html`、`Interaction-Spec.md` | 规格通过；应用未实现 |

## 3. 生命周期权威顺序

1. 项目对齐
2. MRD
3. PRD
4. 方案确认
5. 技术栈确认
6. 分阶段开发（后端 → 前端）
7. MVP
8. 内部验收
9. 种子用户内测
10. BRD / 商业模式确认
11. 发布 / 交接
12. 数据与反馈

`数据与反馈 → 下一轮项目对齐` 创建新的 iteration、ContextVersion 和 Artifact 分支；上一轮历史保持只读。

## 4. 视觉来源与证据边界

- 唯一权威交互视觉基线：[根目录 Harness 表](../../产品工厂Agent_Harness表.html)。其 HTML 源码包含 38/62 双栏、团队群聊、成员/输入/Gate、产物节点/连线、缩放、预览、下载和 URL 操作。
- [子目录 Harness 页面](../../产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html) 是 12 阶段生命周期适配投影，不是新的视觉权威源。
- [应用桌面](./app-desktop.png) / [应用移动](./app-mobile.png) 是 D3 静态 mock 壳历史快照；当前代码只是项目事件列表和线性 Artifact 节点，不符合权威交互基线。
- [生命周期桌面](./lifecycle-desktop.png) / [生命周期移动](./lifecycle-mobile.png) 只对应生命周期阅读页。
- [Harness 移动](./harness-mobile.png) 只是一张历史原型快照，且不足以单独证明根目录权威基线的桌面/移动完整交互。
- 当前没有一套可复现证据证明权威原型或 D3 应用在 `1440×900`、`390×844` 下完成了完整交互符合性验收。因此该项明确记为 **未验收**。

## 5. 本次关闭的归档差异

| 差异 | 处理 |
|---|---|
| `Acceptance-Test-Plan.md` 的 v0.2 一致性重验仍未勾选 | 已勾选并链接本报告 |
| 交互视觉权威源误指向子目录 Harness | 改回根目录 `产品工厂Agent_Harness表.html`；子目录只保留生命周期投影角色 |
| 应用、生命周期和 Harness 截图被混写为统一浏览器证据 | 全部降级为按页面标注的历史快照，不再证明交互符合性 |
| D3 静态事件列表被误认作双栏群聊实现 | 明确记录为不符合权威基线，交互实现/验收均未完成 |
| `Technical-Adaptation.md` 结尾仍使用“冻结候选/批准前”历史措辞 | 更新为已冻结并保留真实实现证据边界 |

## 6. 未被本次复验改变的内容

- 4 个核心 Agent 及其职责、4 份 Prompt、Capability/Skill 注册方式不变。
- 冻结技术栈、DeepSeek 单供应商、本地 Codex CLI Adapter、本机/内网边界不变。
- V1 无向量 RAG、有界 Agent Loop、LangGraph/确定性控制面职责分离不变。
- 开源参考仍按 `Technical-Adaptation.md` 的复用分级执行，不整仓复制。

## 7. 阶段判定

**D1-D2 规格一致性正式归档完成。** 该结论来自冻结文档、用户批准和权威原型源码，不代表浏览器交互验收，也不证明 PostgreSQL、真实 API、DeepSeek、Codex Adapter、正式 React Flow、种子用户或发布已经完成。

当前继续 D3。D3 退出仍缺 PostgreSQL 16 在线连接/migration、真实 API/数据库集成与配置 fail-fast；当前前端交互不符合权威基线，必须在 D4/D8 相应前端退出检查前补齐并真实浏览器验收。
