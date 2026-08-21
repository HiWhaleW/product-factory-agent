# 产品工厂 Agent - 能力注册表

> 版本：v0.1  
> 原则：Agent 是责任主体，Skill 是可执行方法，Tool 是外部行动。V1 仅 4 个核心 Agent。

## 1. 核心 Agent

```typescript
type CoreAgentId = 'factory-lead' | 'ai-pm' | 'builder' | 'reviewer';

interface AgentDefinition {
  id: CoreAgentId;
  promptPath: string;
  allowedStages: ProjectStage[];
  defaultCapabilityIds: string[];
  canProposeStateTransition: boolean;
  canApproveGate: false;
  contextPolicy: 'project-minimum' | 'stage-minimum' | 'clean-review';
}
```

| Agent | Prompt | 进群时机 | 默认能力 | 责任边界 |
|---|---|---|---|---|
| Factory Lead | [factory-lead.prompt.md](./prompts/factory-lead.prompt.md) | 始终在群 | CAP-01/05/06/12 | 可路由、创建 Context Pack、提闸；不可批闸 |
| AI PM | [ai-pm.prompt.md](./prompts/ai-pm.prompt.md) | G0 后、需求/定义阶段 | CAP-02/03/04 | 可产出文档与建议；不可伪造证据/冻结范围 |
| Builder | [builder.prompt.md](./prompts/builder.prompt.md) | G2 后参与方案；G4 后才可开发 | CAP-07/08/09 | 可改受限工作区；不可改产品范围/自主发布 |
| Reviewer | [reviewer.prompt.md](./prompts/reviewer.prompt.md) | 文档红队、QA、发布验证 | CAP-10/11 | 清洁上下文审查；可打回，不可代替业务验收 |

## 2. 能力契约

```typescript
interface CapabilityDefinition {
  id: string;
  name: string;
  ownerAgentIds: CoreAgentId[];
  inputSchemaId: string;
  outputSchemaId: string;
  allowedToolIds: string[];
  allowedStages: ProjectStage[];
  risk: 'low' | 'medium' | 'high';
  requiresGate?: GateId;
  retryPolicy: RetryPolicy;
  skillDescriptors: SkillDescriptor[];
}
```

| ID | 能力 | 默认责任 Agent | Skill/资料 | 工具 | 退出产物 |
|---|---|---|---|---|---|
| CAP-01 | 进件分诊与项目卡 | Factory Lead | AI PM Router / PRD 需求澄清 | 文件读取 | Project Brief |
| CAP-02 | 证据调研 | AI PM | `product-research` | 浏览器/搜索/文件 | Evidence Index |
| CAP-03 | MRD 市场需求评估 | AI PM | `mrd` + `product-research` | 引用校验 | MRD + Red Team Review |
| CAP-04 | PRD 与范围 | AI PM | `prd-writer` + `pm-doc-writer` | 文档产物 | PRD / Review |
| CAP-05 | Agent 路由与 Context Pack | Factory Lead | 身份路由元规则 | 上下文存储 | Context Pack / Handoff |
| CAP-06 | 人工闸和状态建议 | Factory Lead | State/Gate Spec | 无副作用 | GateRequest / TransitionProposal |
| CAP-07 | 交互与技术适配 | Builder | UI Prompt + 三份工程手册 | 仓库读取 | User Flow / Tech Adaptation / API Contract |
| CAP-08 | 受限代码实现 | Builder | 终极开发者 | Codex CLI / 文件 / Git / 终端 | commit / code artifacts / mock tests |
| CAP-09 | 发布准备 | Builder | 部署手册 | 部署适配器 | Release Checklist / Deployment Record |
| CAP-10 | 文档独立审查 | Reviewer | AI PM Review / 文档规范 | 引用/版本校验 | Review Report |
| CAP-11 | 工程与 Agent QA | Reviewer | 测试规则 | pytest / Vitest / Playwright / 真模型 | QA Report / Known Issues |
| CAP-12 | 内测、商业 BRD 与迭代分支 | AI PM + Factory Lead | `brd` + 状态路由 | 数据/事件/日志查询 | Beta Evidence / BRD / Feedback / Iteration Branch |

## 3. 17 岗位到 V1 能力的映射

| 原岗位 | V1 处理 | 所属 |
|---|---|---|
| R01 AI 产品经理 | 合并为核心 Agent | AI PM |
| R02 UI 设计师 | Skill，复杂 UI 可临时 Agent 化 | Builder |
| R03 全栈工程师 | 合并为核心 Agent | Builder |
| R04 数据扒取 | Skill | AI PM |
| R05 运营 | V1 非核心；作反馈/运营 Skill | Factory Lead |
| R06 Reviewer | 合并为核心 Agent | Reviewer |
| R07 CKO | V1 不设独立 Agent；只生成候选经验 | Factory Lead + Governance Review |
| R11 法务 | Skill；高风险转人类法务 | AI PM / Reviewer |
| R12 增长 | V1 非核心；作上线后指标 Skill | Factory Lead |
| R13 财务 | 成本/定价 Skill | AI PM |
| R17 内容创作 | 文档/使用手册 Skill | Factory Lead |
| R18 视频编导 | V1 不加载 | 垂直插件 |
| R19 教育专家 | V1 不加载 | 垂直插件 |
| R20 Prompt 工程师 | Skill，不设独立 Agent | AI PM / Builder |
| R21 在线客服 | V1 不加载 | 上线后插件 |
| R22 客户研究 | Skill，复杂研究可临时 Agent 化 | AI PM |
| R23 客户支持 | V1 只保留反馈分类契约 | Factory Lead |

## 4. 动态 Agent 升格条件

能力包只在任一条件成立时升格为独立 Agent：

1. 需要与主 Agent 不同的最小权限和私有上下文。
2. 需要与其他任务并行运行并后续合流。
3. 需要独立审查，不应继承执行者判断。
4. 用户存在持续 `@Agent` 沟通需求。
5. 产物具有独立退出 Schema 和失败恢复策略。

## 5. 注册表运行规则

- 主 Agent 只能调用 `allowedStages` 包含当前阶段的能力。
- 高风险能力在注册表中必须声明 `requiresGate`。
- 能力输出必须通过 Schema 校验，才能创建 DAG 节点。
- 任何 Agent 不能通过调用另一 Agent 来扩大自己权限。
- Skill 和 Prompt 有独立版本；每次运行记录实际版本。

## 6. Skill 两阶段加载

Agent 默认只看到与当前阶段/能力相符的 Skill 描述，不把所有 Skill 正文塞入系统 Prompt。

```typescript
interface SkillDescriptor {
  skillId: string;
  name: string;
  description: string;
  triggerHints: string[];
  contentRef: string;
  version: string;
  contentHash: string;
  allowedAgentIds: CoreAgentId[];
  allowedStages: ProjectStage[];
}
```

加载协议：

1. Harness 按当前 Agent、阶段、Capability 和 Context Pack 过滤 Skill Descriptor。
2. 模型选择需要的 `skill_id`，Harness 再加载对应正文/必要引用。
3. 运行记录实际 `skill_id/version/content_hash`；未加载的 Skill 不计为本次运行依据。
4. Skill 只能提供方法和知识，不能扩大 Agent 的工具权限、阶段权限或 Gate 权限。
5. Skill 正文及引用按预算截断/分段加载；相对引用必须解析在批准的 Skill 根目录内。
6. Skill 内容视为指令来源，不自动成为项目事实；外部事实仍需 EvidenceRef。

## 7. Agent 任务与运行时关系

```text
Factory Lead 选择 Capability
  → 创建 ExecutionTask + dependencies
  → 生成 Context Pack
  → 目标 Agent 认领 Task
  → 创建 AgentRun
  → 按需加载 Skill / 调用 Tool
  → 提交 Handoff + Artifact refs
  → Reviewer / Gate 决定是否成为阶段证据
```

- Agent 的“入群/自介”是用户可见身份事件，不代表后台常驻线程已经启动。
- 一个 Agent 可以先后执行多个 Task；一个 Task 的重试生成新 Run，不生成新的可见 Agent。
- 并行只在任务无依赖冲突、工作区/预算允许且确有时延收益时启用；V1 默认单 Builder Run。
