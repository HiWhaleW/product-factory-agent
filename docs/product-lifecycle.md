# 产品工厂 Agent - 产品生命周期与 Gate 映射

> 版本：v0.2  
> 日期：2026-08-20  
> 状态：用户已明确修订阶段顺序；本文件是阶段顺序的权威入口  
> HTML 阅读版：[product-lifecycle.html](./product-lifecycle.html)

## 1. 冻结结论

一个产品迭代包含 **12 个用户可见阶段**；“进入下一轮迭代”是循环转移，不作为本轮第 13 个阶段：

1. 项目对齐
2. MRD
3. PRD
4. 方案确认
5. 技术栈确认
6. 分阶段开发
7. MVP
8. 内部验收
9. 种子用户内测
10. BRD / 商业模式确认
11. 发布 / 交接
12. 数据与反馈

完成第 12 阶段后，由反馈创建新分支，回到下一轮“项目对齐”。这条回环不是第 13 个并列阶段。

“分阶段开发”的内部执行顺序固定为 **后端开发 → 前端开发**。它不是一次 Run：后端与前端分别创建 Execution Task、AgentRun、RunStep、测试和 ArtifactVersion；后端退出证据未满足时，前端任务不得进入 `ready`。

## 2. 为什么 BRD 放在种子内测后

本项目中的 BRD 定义为“基于真实种子用户数据确认商业模式的文档”。因此：

- MRD 在开发前证明“谁有何种市场需求、现有替代是什么、证据与反证是什么”。
- PRD 在开发前冻结“产品做什么、不做什么、如何验收”。
- BRD 在种子内测后回答“价值是否成立、由谁付费、成本/定价/推广如何假设、什么情况应 Hold/Kill”。
- 早期只能记录商业假设，不得提前生成“已确认商业模式”的 BRD。

这与传统“BRD → MRD → PRD”的命名惯例不同，因此所有界面和文档必须明确写作“BRD / 商业模式确认”，避免读者误以为是前置立项文档。

## 3. Gate 映射

| Gate | 放行转移 | 人必须确认 | 未通过 |
|---|---|---|---|
| G0 | 项目对齐 → MRD | Project Brief、目标用户、时间、不做范围 | 不进入 MRD |
| G1 | MRD → PRD | 问题/市场需求、证据、反证、替代方案 | 补证据、调整或 Kill |
| G2 | PRD → 方案确认 | MVP 范围、验收标准、反指标 | 不进入方案设计 |
| G3 | 方案确认 → 技术栈确认 | User Flow、交互方案、关键取舍 | 不做技术实现 |
| G4 | 技术栈确认 → 后端开发 | 技术栈、成本、安全、数据边界、回退 | Builder 不开工 |
| G5 | 内部验收 → 种子内测 | MVP 结果、真实 QA、已知问题、内测范围 | 不开放给种子用户 |
| G6 | 商业 BRD → 发布/交接 | 内测数据、商业模式、费用、权限、发布/回滚 | 不正式发布 |

G0-G6 均为产品阶段必审。一次工具动作仍由 `allow / ask / deny` 和 PermissionRequest 控制；产品 Gate 不能替代工具权限。修改全局 Harness/Prompt/Skill 使用独立 Governance Review，不占产品 Gate 编号。

## 4. 状态与开发子阶段

```text
alignment → mrd → prd → solution_confirmation → tech_stack_confirmation
  → development_backend → development_frontend → mvp
  → internal_acceptance → seed_beta → brd → release_handoff → feedback
  → alignment（新 iteration/context/artifact branch）
```

允许回退到受影响的最近阶段，但不改写历史：

- 后端缺陷：回到 `development_backend`。
- 交互缺陷：回到 `development_frontend` 或 `solution_confirmation`。
- 市场假设变化：回到新一轮 `mrd`。
- 商业证据不足：从 `brd` 回到 `seed_beta` 继续取证，或 Kill。

## 5. 产品生命周期与工程排期不是同一轴

| 轴 | 含义 | 当前安排 |
|---|---|---|
| D1-D10 | 开发“产品工厂 Agent”本身的工程日程 | D10 上限为通过 G5 的 Beta Candidate 与可执行内测包 |
| B1-Bn | 用种子用户验证某一项目/产品迭代 | 由样本、任务成功、使用和反馈阈值结束，不硬填天数 |
| 产品 12 阶段 | 产品工厂中每个项目经历的业务生命周期 | 内测后商业 BRD/G6，之后发布、反馈和下一轮 |

不得把 D10 日期当成真实种子数据、商业模式或发布完成的证据。

## 6. D3 当前实现边界

- 确定性状态迁移已经按上述顺序更新，并有“后端不得跳过前端直接到 MVP”的纯逻辑测试。
- 简洁 mock UI 已显示 12 阶段、MRD 当前态、后端→前端开发子阶段和内测后 BRD。
- `docs/evidence/` 中存在应用、生命周期和 Harness 的历史截图，但它们来自不同页面和不同 mock/原型版本，只能证明对应页面当时可见，不能证明权威交互符合性。
- 当前没有一套可复现记录同时证明根目录权威原型与 D3 应用在桌面/移动端的交互符合性；该项保持未验证。
- PostgreSQL 实例、真实 API 集成、DeepSeek、Codex Adapter、种子用户和正式发布仍未完成。
- mock 只用于 D3-D4 可观察性，不能作为 G1-G6 或真实模型/用户验收证据。
