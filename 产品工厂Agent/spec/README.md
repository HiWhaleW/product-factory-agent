# 产品工厂 Agent - D1-D2 规格冻结包

> 版本：v0.2  
> 日期：2026-08-20  
> 状态：已冻结（2026-08-20）  
> 开发周期：10 个工作日  
> 目标执行者：Codex / Claude Code / Cursor

**人类可视化评审入口**：[index.html](./index.html)  
**权威交互视觉基线**：[../../产品工厂Agent_Harness表.html](../../产品工厂Agent_Harness表.html)  
**12 阶段生命周期适配投影**：[../产品工厂Agent_Harness流程与能力注册表.html](../产品工厂Agent_Harness流程与能力注册表.html)（不得替代视觉基线）
**阶段交接入口**：[../../docs/handoff.html](../../docs/handoff.html)

## 30 秒概述

产品工厂 Agent 是面向企业内部产品负责人的 AI 产品交付工具。用户通过项目群聊与主 Agent 对齐目标；主 Agent 按阶段调用 AI PM、Builder、Reviewer 和受控工具；右侧累计 DAG 保留从 Brief、MRD、PRD、方案/技术决定、后端/前端代码、MVP、内测、商业 BRD 到发布、反馈与下一轮分支的全部可追溯产物。

## 冻结决策

| 维度 | V1 决策 |
|---|---|
| 核心 Agent | 主 Agent、AI PM、Builder、Reviewer |
| 用户阶段 | 12 个本轮阶段 + 下一轮迭代循环 |
| 开发顺序 | 分阶段开发内部固定为后端 → 前端 |
| 人工闸 | G0-G6 七个必审；全局回写走独立 Governance Review |
| 用户范围 | 单用户/单管理员内部试用 |
| 模型范围 | DeepSeek 单供应商；渠道、模型名、Base URL 最晚 D5 真模型切片前锁定并冒烟，不做智能多模型路由 |
| Builder 运行时 | Codex CLI 适配器 + 每项目受限工作区 |
| 部署 | 本机/内网运行；V1 不将代码执行放在 veFaaS |
| 画布 | React Flow 产物 DAG，非自由白板 |
| 共享上下文 | 版本化 Context Pack + 最小权限 |

## 文件导航

| 文件 | 用途 | 开发时机 |
|---|---|---|
| [PRD.md](../../docs/PRD.md) | 用户、范围、核心闭环、指标与 Roadmap | 首次启动必读 |
| [PRD-Agent-Blueprint-Adaptation.md](../../docs/PRD-Agent-Blueprint-Adaptation.md) / [HTML](../../docs/PRD-Agent-Blueprint-Adaptation.html) | Agent Blueprint 参考裁决、7 层架构、贯穿数据流与分层验收 | Spec Freeze 架构评审 |
| [Interaction-Spec.md](./Interaction-Spec.md) | 双栏界面、群聊、@Agent、DAG 与预览 | 前端/交互必读 |
| [Frontend-Implementation-Spec.md](./Frontend-Implementation-Spec.md) / [HTML](./Frontend-Implementation-Spec.html) | 页面线框、组件树、事件投影、全状态、响应式与 D3-D8 前端任务 | 前端实施/验收必读 |
| [Context-Schema.md](./Context-Schema.md) | 共享上下文分层、Context Pack 与合并规则 | Agent 编排必读 |
| [State-Machine-and-Gates.md](./State-Machine-and-Gates.md) | 项目状态、迁移、人工闸与反馈分支 | 后端/编排必读 |
| [Capability-Registry.md](./Capability-Registry.md) | 4 Agent、Skill、工具、输入/输出契约 | Agent 实现必读 |
| [Tool-and-Permission-Policy.md](./Tool-and-Permission-Policy.md) | 工具白名单、预算、密钥、不可逆操作 | 执行层必读 |
| [Technical-Adaptation.md](./Technical-Adaptation.md) / [HTML](./Technical-Adaptation.html) | 已冻结技术栈；环境、数据、API 和部署仍按真实实现证据逐项确认 | 开工前必读 |
| [Acceptance-Test-Plan.md](./Acceptance-Test-Plan.md) / [HTML](./Acceptance-Test-Plan.html) | 自动测试、真模型冒烟、浏览器 QA 与人工验收 | 每阶段放行必读 |
| [Engineering-Schedule.md](./Engineering-Schedule.md) | D1-D10 每日任务、依赖、人工闸、缓冲和完成定义 | 工程排期唯一详细来源 |
| [Competitor-and-OpenSource-Research.md](./Competitor-and-OpenSource-Research.md) | 直接/间接竞品和 GitHub 技术参考 | 产品/技术决策溯源 |
| [Agent-Prompt-Gap-Report.md](./Agent-Prompt-Gap-Report.md) | 现有 Prompt 覆盖、缺口与生成可行性 | Prompt 实现前必读 |
| [Harness-Reference-Assessment.md](./Harness-Reference-Assessment.md) | `learn-claude-code-main` 17 章机制裁决与规格增量 | Harness/运行时实现前必读 |
| [D1-D2 一致性复验归档](../../docs/evidence/d1-d2-consistency-revalidation.md) / [HTML](../../docs/evidence/d1-d2-consistency-revalidation.html) | 4 Agent、12 阶段、G0-G6、Context Pack、双 DAG；明确分离规格一致性与未完成的浏览器符合性 | D1-D2 规格归档证据 |

**可视化参考评估**：[Harness-Reference-Assessment.html](./Harness-Reference-Assessment.html)
**可视化工程排期**：[Engineering-Schedule.html](./Engineering-Schedule.html)

## 核心 Prompt

- [prompts/factory-lead.prompt.md](./prompts/factory-lead.prompt.md)
- [prompts/ai-pm.prompt.md](./prompts/ai-pm.prompt.md)
- [prompts/builder.prompt.md](./prompts/builder.prompt.md)
- [prompts/reviewer.prompt.md](./prompts/reviewer.prompt.md)

## 10 工作日 Roadmap 摘要

每日任务、外部依赖、人工投入、风险缓冲和完成定义以 [Engineering-Schedule.md](./Engineering-Schedule.md) 为唯一详细来源。

| 日期 | 里程碑 | 放行证据 |
|---|---|---|
| D1-D2 | 规格冻结 | 本文档包通过 Spec Freeze Review |
| D3-D4 | 项目/群聊/Context/产物/闸口 + Task/Run/Permission 最小控制面 | 本地 API + 数据持久化通过 |
| D5-D6 | 定义纵向切片 | 对齐 → MRD/G1 → PRD/G2 → 方案/G3 → 技术栈/G4 |
| D7-D8 | Builder 与 MVP | 后端 → 前端 → MVP Candidate |
| D9 | 独立 QA | Reviewer、真模型、浏览器、恢复和安全回归 |
| D10 | 内部验收 | G5、Beta Candidate、种子内测计划与数据采集契约 |
| B1-Bn | 证据驱动验证 | 真实种子内测 → 商业 BRD/G6 → 发布/交接 → 反馈与新迭代 |

## 加载规则

1. 开工时先读本文件、`../../docs/PRD.md`、`Technical-Adaptation.md`。
2. 实现 Agent 编排时再读 Context、State、Capability、Tool Policy 和 Harness Reference Assessment。
3. 实现前端时读 `Interaction-Spec.md` 和 `Frontend-Implementation-Spec.md`。
4. 工程实施前读 `Engineering-Schedule.md`，任何阶段完成前读 `Acceptance-Test-Plan.md`。
5. 不要一次将所有文档放入模型上下文。

## Spec Freeze Review 批准记录

- [x] 同意 V1 仅单用户/单管理员。
- [x] 同意 V1 仅 DeepSeek 一个模型供应商；接入渠道、模型名和 Base URL 最晚 D5 真模型切片前锁定并冒烟。
- [x] 同意 V1 使用本地 Codex CLI 作为 Builder 执行适配器。
- [x] 同意 V1 优先本机/内网发布，不实现企业 SSO、多租户或云代码沙箱。

批准时间：2026-08-20。用户同时批准实施顺序调整为“后端控制面优先，前端 D3-D4 先做简洁可观察渲染，最终必须满足基本渲染和浏览器验收”。

流程修订记录：用户于 2026-08-20 明确纠正阶段顺序；v0.2 以 12 阶段循环、后端→前端开发和内测后商业 BRD 为准。Artifact DAG/Execution Task DAG、Gate/PermissionRequest、Context Pack/Run 压缩仍保持分离。
