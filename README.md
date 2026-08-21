# 产品工厂 Agent

> 当前阶段：D5 定义链路进行中  
> 最后同步：2026-08-22  
> 开发状态：Factory Lead 真实产品切片已到 `waiting_g0`；隔离 fixture 已真实贯通博查、AI PM、Evidence/MRD 落库、Reviewer、Red Team Review 和 G1 打开；真实产品 G0/G1 仍未决定

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
| HTML | 权威交互基线、生命周期投影、规格评审、架构与交接 | 文件存在；D3 应用已有真实浏览器检查，但截图归档和权威原型完整复验仍缺，不宣称完整视觉验收通过 |
| 应用代码 | FastAPI/Next.js monorepo、真实项目列表与单屏双栏工作区 | 后端已实现并以隔离真实纵向冒烟验证 Factory Lead、AI PM 提交、Reviewer clean-review、Red Team Review 与 G1 open |
| 数据库/API/迁移 | PostgreSQL 16.15、D5 migration、控制面 API | 42 条真实 PostgreSQL 集成/并发/恢复测试通过；migration 已到 `20260822_0004` 并完成往返 |
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

## 下一步

**D5 正在进行。隔离 fixture 已真实贯通 AI PM Permission/checkpoint、博查、Evidence/MRD 持久化、Reviewer Red Team Review 和 G1 open；G1 未代批，fixture 仍为 `mrd / Context v2`。Factory Lead 的真实产品项目仍在 `alignment` 等待 G0 人审。当前证据不等于完整 D5、Builder、MVP 或内测通过。**

需要用户确认：

- [x] V1 仅单用户/单管理员。
- [x] V1 仅 DeepSeek 一个模型供应商；接入渠道、模型名和 Base URL 最晚 D5 真模型切片前锁定并冒烟。
- [x] V1 Builder 使用本地 Codex CLI 适配器。
- [x] V1 优先本机/内网运行，不做 SSO、多租户或云代码沙箱。

当前已完成 PostgreSQL migration `20260822_0004`、42 项在线集成/并发/恢复测试，以及 DeepSeek/Runtime/Factory Lead/博查/隔离 AI PM + Reviewer 真实冒烟。契约：[博查](./docs/contracts/d5-bocha-web-research-contract-2026-08-22.html) / [AI PM→Reviewer→G1](./docs/contracts/d5-review-candidate-contract-2026-08-22.html)。脱敏证据：[AI PM/Reviewer JSON](./docs/evidence/d5-ai-pm-research-smoke-2026-08-22.json) / [Runtime](./docs/evidence/d5-agent-runtime-progress-2026-08-22.html) / [DeepSeek](./docs/evidence/d5-deepseek-smoke-2026-08-22.html)。这不代表 G1 已决定、Builder 或完整 D5 已通过。

## 文档权威顺序

1. 用户本轮确认。
2. `产品工厂Agent/spec/` 权威规格。
3. `docs/` 当前交接/架构/运维摘要。
4. 根目录三份原始手册。

规格中的 API、数据表、路由和环境变量是**目标契约**，不是当前已实现能力。
