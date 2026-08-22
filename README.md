# 产品工厂 Agent

> 当前阶段：产品状态 `prd / Context v3 / iteration v1`；真实 PRD 已保存，G2 等待用户决定  
> 最后同步：2026-08-23  
> 开发状态：AI PM PRD 与 Reviewer 已真实运行；PRD/Review v1 已落库，G2 已打开但未决定；Builder 未启动

产品工厂 Agent 是面向企业内部产品负责人的 AI 产品交付工具。用户在项目群聊中与主 Agent 对齐目标；AI PM、Builder、Reviewer 按阶段入群；Context Pack 控制共享上下文；右侧累计 DAG 保留从 Brief、MRD、PRD、方案/技术决定、后端/前端代码、MVP、内测、商业 BRD 到发布、反馈和下一轮分支的全部产物。

## 5 分钟入口

1. 人类交接首页：[docs/handoff.html](./docs/handoff.html)
2. 当前交接文档：[docs/handoff.md](./docs/handoff.md)
3. 可直接给下一位 Agent 的提示词：[docs/HANDOFF_PROMPT.md](./docs/HANDOFF_PROMPT.md)
4. D1-D2 规格可视化评审：[产品工厂Agent/spec/index.html](./产品工厂Agent/spec/index.html)
5. 权威交互视觉基线：[产品工厂Agent_Harness表.html](./产品工厂Agent_Harness表.html)
6. 生命周期适配投影（不替代视觉基线）：[产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html](./产品工厂Agent/产品工厂Agent_Harness流程与能力注册表.html)
7. Harness 参考可视化评估：[产品工厂Agent/spec/Harness-Reference-Assessment.html](./产品工厂Agent/spec/Harness-Reference-Assessment.html)
8. 10 工作日工程排期：[产品工厂Agent/spec/Engineering-Schedule.html](./产品工厂Agent/spec/Engineering-Schedule.html)
9. 7 层架构适配 PRD：[docs/PRD-Agent-Blueprint-Adaptation.html](./docs/PRD-Agent-Blueprint-Adaptation.html)
10. 前端实施规格：[产品工厂Agent/spec/Frontend-Implementation-Spec.html](./产品工厂Agent/spec/Frontend-Implementation-Spec.html)
11. 当前事实审计：[docs/evidence/implementation-truth-audit.html](./docs/evidence/implementation-truth-audit.html)

## 当前实际存在的东西

| 类别 | 已有 | 状态 |
|---|---|---|
| 原始工程约束 | 3 份技术/前端/部署手册 | 已阅读并裁决适用/偏离 |
| D1-D2 规格 | 11 份核心产品/执行/排期规格 | 四项边界已冻结；2026-08-20 按用户纠正升级为 12 阶段循环 |
| 调研 | 竞品/GitHub、Prompt 缺口、标准 Harness 参考评估 | 已完成；参考评估基于本地源码/测试设计，测试未在本机执行通过 |
| Agent Prompt | Factory Lead、AI PM、Builder、Reviewer | v0.2 冻结；Factory Lead / Reviewer 已真实运行，不等于 4 Agent 整体效果通过 |
| HTML / 前端视觉 | 权威交互基线、统一首页/工作区/设置页、规格评审、架构与交接 | 当前桌面为用户最新确认的约 `30/70` 双栏；生产模式桌面 `1440×900` 与移动 `390×844` 已用 ego-lite 完成统一导航和核心交互 QA，截图/JSON 已归档，用户已确认当前前端无问题；不代表视觉永久冻结或完整产品验收完成 |
| 应用代码 | FastAPI/Next.js monorepo、真实项目列表与单屏双栏工作区 | Factory Lead、AI PM、Reviewer 的真实链路已到 PRD Review/G2 open；Builder 未启动 |
| 数据库/API/迁移 | PostgreSQL 16.15、D5-D6 控制面 API | 44 条真实 PostgreSQL 集成/并发/恢复测试通过；migration 已到 `20260822_0006`；真实 PRD/Review/G2、Run/Step/Tool/cursor 与可回收 Gate/Permission fixture 已存在 |
| 公开搜索 | 博查 Web Search Adapter、稳定 EvidenceRef、billable Permission | 真实认证/大陆网络/中文 Schema/短超时与 AI PM checkpoint 恢复通过；429/费用未观察 |
| DeepSeek | 异步 Adapter、SecretRef、Schema/工具/SSE/错误类型 | 7 类真实冒烟通过（含 context-too-long）；真实 429 未观察，Provider 未返回费用 |
| 部署 | 无 | 真实种子内测和商业 BRD/G6 通过后才允许正式发布 |

## 项目目录

```text
.
├── README.md                       # 人类首页
├── AGENTS.md                       # Codex/开发 Agent 约束
├── docs/
│   ├── handoff.html                   # 可视化交接首页
│   ├── handoff.md                     # 当前交接状态
│   ├── HANDOFF_PROMPT.md              # 交给下一位 Agent 的提示词
│   ├── materials-inventory.md         # 素材全量索引
│   ├── architecture.md                # 架构与关键决策
│   └── operator-runbook.md            # 环境/运行/排障
├── 产品工厂Agent/
│   ├── 产品工厂Agent_Harness流程与能力注册表.html
│   └── spec/                           # D1-D2 权威规格与 Prompt
└── AI*.md                         # 原始工程手册
```

## 当前统一执行线

1. **已完成本次任务切片：** GitHub Connector 安全快照；销售复盘项目恢复到 Web 同源 PostgreSQL/API；Artifact v1/v2、G1、known issues、执行/恢复、Gate 决定和 Session 投影；Web 真实版本切换与生产模式 QA。
2. **不再等待跨线并入：** Agent Runtime、FastAPI 和 Next.js 后续由同一任务在当前工作区直接修改、联调、测试和更新文档。局部改动必须形成 API → Web → 数据库/事件的完整证据。
3. **当前下一项：** 等待用户决定真实 G2 `fdac9cd1-3cb8-4a98-b87d-18d8ef779e82`；批准后再推进方案/G3、技术栈/G4。
4. **Builder 边界：** G4 前禁止启动；G4 后固定后端开发 → 前端开发，再进入 MVP、G5、种子内测、BRD/G6 和发布。

## 当前下一步

**销售复盘 Agent 已用真实 DeepSeek 完成 AI PM PRD Run 和 Reviewer clean-review；PRD v1、PRD Review v1 已确定性持久化，G2 已打开但未决定。首次 PRD 输出因 Schema 缺字段被 fail-closed，未写入业务数据；修正后才重跑成功。当前证据不等于 Builder、MVP、内测或发布通过。**

需要用户确认：

- [x] V1 仅单用户/单管理员。
- [x] V1 仅 DeepSeek 一个模型供应商；接入渠道、模型名和 Base URL 最晚 D5 真模型切片前锁定并冒烟。
- [x] V1 Builder 使用本地 Codex CLI 适配器。
- [x] V1 优先本机/内网运行，不做 SSO、多租户或云代码沙箱。

当前统一工作区已通过 `pnpm check`：Web 13/13、Python 60 passed；PostgreSQL 在线集成 44/44；Next.js production build 通过；Alembic 为 `20260822_0006 (head)`。真实 PRD 证据：[HTML](./docs/evidence/d5-prd-runtime-progress-2026-08-23.html) / [JSON](./docs/evidence/d5-prd-runtime-flow-2026-08-23.json)。联合验收 fixture 项目为 `c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001`。底层 `2500ms` cursor 仍是降级轮询，AG-UI/SSE 未完成。

## 文档权威顺序

1. 用户本轮确认。
2. `产品工厂Agent/spec/` 权威规格。
3. `docs/` 当前交接/架构/运维摘要。
4. 根目录三份原始手册。

规格中的 API、数据表、路由和环境变量是**目标契约**，不是当前已实现能力。
