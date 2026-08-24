import type { ArtifactNode, ProjectEvent } from "@/lib/contracts";
import { projectInternalStageLabel } from "./stages";

export type EventTone = "agent" | "artifact" | "control" | "run" | "tool" | "unknown";

export type EventPresentation = {
  label: string;
  summary: string;
  tone: EventTone;
};

export type VisibleRunState = {
  label: string;
  tone: "live" | "warning" | "error";
};

export type ReferencedMessage = {
  body: string;
  reference: {
    artifactId: string;
    title: string;
    version: number;
  } | null;
};

export type StageProcessGroup = {
  id: string;
  state: string;
  label: string;
  events: ProjectEvent[];
};

export type FriendlyProcessStep = {
  label: string;
  summary: string;
};

export type ProjectAgentProfile = {
  id: string;
  name: string;
  label: string;
  avatar: string;
  tone: "lead" | "pm" | "builder" | "reviewer";
  aliases: readonly string[];
  introduction: string;
};

export const projectAgentProfiles: readonly ProjectAgentProfile[] = [
  {
    id: "factory-lead",
    name: "Factory Lead",
    label: "主 Agent",
    avatar: "主",
    tone: "lead",
    aliases: ["factory lead", "factory-lead", "factory_lead"],
    introduction: "我是 Factory Lead（主 Agent）。我负责项目对齐、阶段推进、Gate 协调和任务分派。需求不清、阶段卡住或不知道找谁时，可以 @Factory Lead。",
  },
  {
    id: "ai-pm",
    name: "AI PM",
    label: "AI PM",
    avatar: "PM",
    tone: "pm",
    aliases: ["ai pm", "ai-pm", "ai_pm"],
    introduction: "我是 AI PM。我的功能是用户与市场研究、证据整理、MRD 和 PRD 定义。需求范围、用户价值或产品定义有问题时，可以 @AI PM。",
  },
  {
    id: "builder",
    name: "Builder",
    label: "Builder",
    avatar: "建",
    tone: "builder",
    aliases: ["builder"],
    introduction: "我是 Builder。我的功能是方案设计、技术实现、测试和交付，只在 Gate 允许后写代码。方案、技术栈、开发或修复问题，可以 @Builder。",
  },
  {
    id: "reviewer",
    name: "Reviewer",
    label: "Reviewer",
    avatar: "审",
    tone: "reviewer",
    aliases: ["reviewer"],
    introduction: "我是 Reviewer。我的功能是独立评审、风险识别、验收和质量把关。不确定是否达标、证据是否充分或需要复核时，可以 @Reviewer。",
  },
] as const;

export function formatProjectVersion(version: number) {
  return `V${version}.0`;
}

export function artifactVersionOptions(latestVersion: number) {
  return Array.from({ length: Math.max(0, latestVersion) }, (_, index) => latestVersion - index);
}

function payloadText(event: ProjectEvent, key: string) {
  const value = event.payload[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function payloadSummary(event: ProjectEvent) {
  return payloadText(event, "summary") || payloadText(event, "user_message");
}

export function projectAgentProfile(value: unknown) {
  if (typeof value !== "string") return null;
  const normalized = value.toLowerCase();
  return projectAgentProfiles.find((profile) => (
    profile.aliases.some((alias) => normalized === alias || normalized.includes(alias))
  )) ?? null;
}

export function agentIntroduction(event: ProjectEvent) {
  if (event.event_type !== "agent.joined") return null;
  const profile = projectAgentProfile(event.payload.agent_name)
    ?? projectAgentProfile(event.payload.agent_id);
  if (!profile) return null;
  return { profile, text: profile.introduction };
}

export function stageStartEventId(events: ProjectEvent[], states: readonly string[]) {
  const stateSet = new Set(states);
  return events.find((event) => {
    if (event.event_type === "project.created") return stateSet.has("alignment");
    return event.event_type === "project.state_changed"
      && typeof event.payload.state === "string"
      && stateSet.has(event.payload.state);
  })?.id ?? null;
}

export function isChatMilestoneEvent(event: ProjectEvent) {
  return event.event_type === "project.created"
    || event.event_type === "project.state_changed"
    || event.event_type === "agent.joined";
}

function processGroupNeedsBreak(group: StageProcessGroup, event: ProjectEvent) {
  const previous = group.events.at(-1);
  if (!previous) return false;
  if (event.event_type === "run.started" && group.events.some((item) => item.event_type.startsWith("run."))) {
    return true;
  }
  const gapMs = new Date(event.created_at).getTime() - new Date(previous.created_at).getTime();
  return gapMs < 0 || gapMs > 60_000;
}

export function groupProcessEventsForConversation(events: ProjectEvent[]): StageProcessGroup[] {
  const groups: StageProcessGroup[] = [];
  const runGroups = new Map<string, StageProcessGroup>();
  let currentState = "alignment";
  let currentGroup: StageProcessGroup | null = null;

  [...events].sort((left, right) => left.sequence - right.sequence).forEach((event) => {
    if (event.event_type === "project.created") {
      currentState = "alignment";
      currentGroup = null;
      return;
    }
    if (event.event_type === "project.state_changed") {
      if (typeof event.payload.state === "string") currentState = event.payload.state;
      currentGroup = null;
      return;
    }
    if (event.event_type === "message.created" || event.event_type === "agent.joined") {
      currentGroup = null;
      return;
    }
    const runId = payloadText(event, "run_id") || payloadText(event, "source_run_id");
    const existingRunGroup = runId ? runGroups.get(runId) : null;
    if (existingRunGroup) {
      existingRunGroup.events.push(event);
      return;
    }

    if (currentGroup && processGroupNeedsBreak(currentGroup, event)) currentGroup = null;

    if (!currentGroup) {
      currentGroup = {
        id: `process-${currentState}-${event.sequence}`,
        state: currentState,
        label: projectInternalStageLabel(currentState),
        events: [],
      };
      groups.push(currentGroup);
    }
    currentGroup.events.push(event);
    if (runId) runGroups.set(runId, currentGroup);
  });

  return groups;
}

export function processActorProfile(events: ProjectEvent[]) {
  for (const event of events) {
    const profile = projectAgentProfile(event.payload.agent_id)
      ?? projectAgentProfile(event.payload.recipient_agent_id)
      ?? projectAgentProfile(event.payload.actor_id);
    if (profile) return profile;
  }
  return null;
}

function friendlyToolName(event: ProjectEvent) {
  const toolId = payloadText(event, "tool_id") || payloadText(event, "tool_name");
  if (toolId === "web_research") return "网络搜索工具：博查";
  if (toolId === "artifact_store") return "产物保存工具";
  if (toolId === "codex_cli") return "代码实现工具：Codex";
  return "任务工具";
}

export function friendlyProcessStep(event: ProjectEvent): FriendlyProcessStep {
  const eventType = event.event_type;
  const profile = projectAgentProfile(event.payload.agent_id)
    ?? projectAgentProfile(event.payload.recipient_agent_id);
  const actor = profile?.label ?? "Agent";

  if (eventType === "context.pack_created") {
    return { label: "准备资料", summary: `已准备好本次任务需要的项目信息。接下来由 ${actor} 处理。` };
  }
  if (eventType === "context.updated") {
    return { label: "更新项目记录", summary: "已记录最新决定，并同步项目进度。" };
  }
  if (eventType === "factory_lead.invocation.started") {
    return { label: "理解你的需求", summary: "主 Agent 正在理解你的目标、范围和限制。" };
  }
  if (eventType === "factory_lead.invocation.completed") {
    return { label: "整理回复", summary: "主 Agent 已整理完成，准备回复你。" };
  }
  if (eventType === "run.started") {
    return { label: "开始处理", summary: `${actor} 正在理解并处理这次任务。` };
  }
  if (eventType === "run.completed") {
    return { label: "完成处理", summary: "本次处理已完成，结果已准备好。" };
  }
  if (eventType === "run.waiting") {
    return { label: "等待继续", summary: "处理暂时停下，正在等待必要的信息或授权。" };
  }
  if (eventType === "run.failed") {
    return { label: "处理未完成", summary: "本次处理遇到问题，记录已保留，可以修正后继续。" };
  }
  if (eventType === "run.recovery_recorded") {
    return { label: "恢复任务进度", summary: "已核对历史执行记录，可以从安全位置继续。" };
  }
  if (eventType === "clarification.recorded") {
    return { label: "整理待确认问题", summary: "发现一项需要你补充确认的信息。" };
  }
  if (eventType === "clarification.answered") {
    return { label: "读取你的回答", summary: "已收到并整理一项补充信息。" };
  }
  if (eventType === "project_brief.created") {
    return { label: "生成项目说明", summary: "已把目标、范围和成功标准整理成项目说明。" };
  }
  if (eventType === "project_brief.approved") {
    return { label: "确认项目说明", summary: "项目目标与范围已获得确认。" };
  }
  if (eventType === "permission.opened") {
    const tool = payloadText(event, "tool_id") === "web_research" ? "网络搜索工具：博查" : "外部工具";
    return { label: "申请工具授权", summary: `使用${tool}前，正在等待一次授权。` };
  }
  if (eventType === "permission.decided") {
    return payloadText(event, "decision") === "allow"
      ? { label: "获得工具授权", summary: "已获得这一次工具使用授权。" }
      : { label: "工具未获授权", summary: "本次工具使用没有获得授权，项目阶段不会改变。" };
  }
  if (eventType.startsWith("tool_run.")) {
    const tool = friendlyToolName(event);
    if (eventType.endsWith("recovered")) return { label: `调用${tool}`, summary: `${tool}已完成，结果已交回 Agent。` };
    if (eventType.endsWith("started")) return { label: `调用${tool}`, summary: `${tool}正在执行。` };
    if (eventType.endsWith("completed")) return { label: `${tool}完成`, summary: "工具结果已安全保存并交回 Agent。" };
    if (eventType.endsWith("failed")) return { label: `${tool}未完成`, summary: "工具执行遇到问题，错误已记录，可以修正后重试。" };
  }
  if (eventType.startsWith("artifact.")) {
    return eventType === "artifact.versioned"
      ? { label: "更新产物", summary: "已保存一版新的产物内容，旧版本仍然保留。" }
      : { label: "保存产物", summary: "已把新的阶段产物保存到右侧画布。" };
  }
  if (eventType === "gate.opened") {
    return { label: "等待阶段确认", summary: "阶段材料已准备好，正在等待你决定是否继续。" };
  }
  if (eventType === "gate.decided") {
    return { label: "记录阶段决定", summary: "已记录你的选择，并准备更新项目阶段。" };
  }
  if (eventType === "task.ready") {
    return { label: "准备下一项任务", summary: "下一项任务已准备好，可以按计划开始执行。" };
  }
  if (eventType.endsWith(".submitted")) {
    return { label: "提交检查", summary: "已把当前阶段产物交给 Reviewer 独立检查。" };
  }
  if (eventType.endsWith(".reviewed")) {
    return { label: "完成独立检查", summary: "Reviewer 已完成检查并记录结果。" };
  }
  return { label: "完成内部处理", summary: "已完成一项必要的内部处理。" };
}

export function eventPresentation(event: ProjectEvent): EventPresentation {
  const summary = payloadSummary(event);
  const eventType = event.event_type;

  if (eventType === "project.created") {
    return { label: "项目事件", summary: summary || "项目已创建，当前停留在项目对齐阶段。", tone: "control" };
  }
  if (eventType === "project.state_changed") {
    const state = payloadText(event, "state");
    return {
      label: "阶段变化",
      summary: summary || `项目阶段已更新为 ${state ? projectInternalStageLabel(state) : "未知状态"}。`,
      tone: "control",
    };
  }
  if (eventType === "agent.joined") {
    return {
      label: "Agent 入群",
      summary: summary || `${payloadText(event, "agent_name") || payloadText(event, "agent_id") || "Agent"} 已加入项目群聊。`,
      tone: "agent",
    };
  }
  if (eventType.startsWith("run.")) {
    return {
      label: `Agent Run · ${eventType.slice(4)}`,
      summary: summary || `Run ${payloadText(event, "run_id") || "状态"} 已更新。`,
      tone: "run",
    };
  }
  if (eventType.startsWith("tool_run.") || eventType.startsWith("task.")) {
    const tool = payloadText(event, "tool_name") || payloadText(event, "capability_id") || "执行任务";
    return {
      label: eventType.startsWith("tool_run.") ? "工具调用" : "执行任务",
      summary: summary || `${tool} · ${eventType.split(".").at(-1) || "状态更新"}`,
      tone: "tool",
    };
  }
  if (eventType.startsWith("artifact.")) {
    return {
      label: "产物更新",
      summary: summary || `${payloadText(event, "title") || "产物"} 已写入累计 Artifact DAG。`,
      tone: "artifact",
    };
  }
  if (eventType === "gate.opened") {
    return {
      label: "等待你选择",
      summary: summary || `${payloadText(event, "gate_type") || "产品 Gate"} 已打开，请在对话中作出决定。`,
      tone: "control",
    };
  }
  if (eventType === "gate.decided") {
    return {
      label: "Gate 决定",
      summary: summary || `${payloadText(event, "gate_id") || "Gate"} 已记录 ${payloadText(event, "decision") || "决定"}。`,
      tone: "control",
    };
  }
  if (eventType === "permission.decided") {
    return {
      label: "Permission 决定",
      summary: summary || `一次性权限已记录 ${payloadText(event, "decision") || "决定"}；项目阶段不变。`,
      tone: "control",
    };
  }
  return { label: eventType, summary: summary || `控制面事件 #${event.sequence}`, tone: "unknown" };
}

export function visibleRunState(events: ProjectEvent[]): VisibleRunState {
  const latest = events.findLast((event) => event.event_type.startsWith("run."));
  if (!latest) return { label: "Agent 未接入", tone: "warning" };

  const status = latest.event_type.slice(4);
  if (["started", "running", "resumed", "streaming"].includes(status)) {
    return { label: "Run 运行中", tone: "live" };
  }
  if (["waiting", "waiting_for_human", "paused", "blocked"].includes(status)) {
    return { label: "Run 等待用户", tone: "warning" };
  }
  if (["failed", "cancelled", "timed_out"].includes(status)) {
    return { label: `Run ${status}`, tone: "error" };
  }
  if (status === "completed") return { label: "Run 已完成", tone: "live" };
  return { label: `Run ${status}`, tone: "warning" };
}

export function composeReferencedMessage(draft: string, artifact: ArtifactNode | null) {
  const content = draft.trim();
  if (!artifact) return content;
  return `【引用产物｜${artifact.title}｜v${artifact.latest_version}｜artifact:${artifact.id}】\n${content}`;
}

export function parseReferencedMessage(content: string): ReferencedMessage {
  const match = content.match(/^【引用产物｜(.+?)｜v(\d+)｜artifact:([^】]+)】(?:\r?\n)?([\s\S]*)$/);
  if (!match) return { body: content, reference: null };
  return {
    body: match[4],
    reference: {
      artifactId: match[3],
      title: match[1],
      version: Number(match[2]),
    },
  };
}
