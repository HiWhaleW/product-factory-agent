import type { ArtifactNode, Project, ProjectEvent } from "@/lib/contracts";
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
    introduction: "我是主 Agent。我负责理解你的目标、推动项目、分派任务，并在需要你决定时停下来说清楚。",
  },
  {
    id: "ai-pm",
    name: "AI PM",
    label: "AI PM",
    avatar: "PM",
    tone: "pm",
    aliases: ["ai pm", "ai-pm", "ai_pm"],
    introduction: "我是 AI PM。我会调研用户和市场、整理事实与判断，再把它们写成 MRD 和 PRD。现在我会按主 Agent 交代的任务开始工作。",
  },
  {
    id: "builder",
    name: "Builder",
    label: "开发 Agent",
    avatar: "建",
    tone: "builder",
    aliases: ["builder"],
    introduction: "我是开发 Agent。我会把已确认的产品方案做成可用的产品，并完成检查和交付。没有你的阶段确认，我不会擅自开始。",
  },
  {
    id: "reviewer",
    name: "Reviewer",
    label: "审查 Agent",
    avatar: "审",
    tone: "reviewer",
    aliases: ["reviewer"],
    introduction: "我是审查 Agent。我会独立检查产物是否达到要求、有哪些风险和还需要改什么。我的检查不会代替你做决定。",
  },
] as const;

export function artifactPanelTitle(project: Pick<Project, "name">) {
  return project.name;
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
  if (toolId === "web_research") return "网络搜索";
  if (toolId === "artifact_store") return "保存产物";
  if (toolId === "codex_cli") return "开发工作";
  return "这项工作";
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
    const tool = payloadText(event, "tool_id") === "web_research" ? "网络搜索" : "外部服务";
    return { label: "等待你决定", summary: `使用${tool}前，需要你允许这一次使用。` };
  }
  if (eventType === "permission.decided") {
    return payloadText(event, "decision") === "allow"
      ? { label: "已获得允许", summary: "你已允许这一次使用。" }
      : { label: "你选择了不允许", summary: "这次使用已停止，项目仍停留在当前阶段。" };
  }
  if (eventType.startsWith("tool_run.")) {
    const tool = friendlyToolName(event);
    if (eventType.endsWith("recovered")) return { label: `继续${tool}`, summary: `${tool}已完成，结果已交给负责的 Agent。` };
    if (eventType.endsWith("started")) return { label: `开始${tool}`, summary: `${tool}正在进行。` };
    if (eventType.endsWith("completed")) return { label: `${tool}已完成`, summary: "结果已保存并交给负责的 Agent。" };
    if (eventType.endsWith("failed")) return { label: `${tool}未完成`, summary: "处理遇到问题，记录已保留，可以修正后重试。" };
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
  if (eventType === "task.delegated") {
    return { label: "主 Agent 已分派任务", summary: `任务要求和相关项目资料已同步给 ${actor}。` };
  }
  if (eventType === "task.delegation_blocked") {
    return { label: "等待完成设置", summary: `${actor} 已接到任务，但当前账户的服务还没有配置完成。` };
  }
  if (eventType === "task.delegation_failed") {
    return { label: "任务启动失败", summary: `${actor} 的任务已保留，修复配置后可以重新启动。` };
  }
  if (eventType.endsWith(".submitted")) {
    return { label: "提交检查", summary: "已把当前阶段产物交给审查 Agent 独立检查。" };
  }
  if (eventType.endsWith(".reviewed")) {
    return { label: "完成独立检查", summary: "审查 Agent 已完成检查并记录结果。" };
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
      label: "处理进展",
      summary: summary ? plainLanguageAgentMessage(summary) : "任务处理进展已更新。",
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
      summary: summary || `${payloadText(event, "title") || "产物"} 已保存到右侧产物区。`,
      tone: "artifact",
    };
  }
  if (eventType === "gate.opened") {
    return {
      label: "等待你选择",
      summary: summary ? plainLanguageAgentMessage(summary) : "阶段材料已准备好，请在对话中作出决定。",
      tone: "control",
    };
  }
  if (eventType === "gate.decided") {
    return {
      label: "阶段决定",
      summary: summary ? plainLanguageAgentMessage(summary) : "你的阶段决定已记录。",
      tone: "control",
    };
  }
  if (eventType === "permission.decided") {
    return {
      label: "本次选择",
      summary: summary ? plainLanguageAgentMessage(summary) : "你的选择已记录，项目仍停留在当前阶段。",
      tone: "control",
    };
  }
  return { label: eventType, summary: summary || `控制面事件 #${event.sequence}`, tone: "unknown" };
}

export function visibleRunState(events: ProjectEvent[]): VisibleRunState {
  const latest = events.findLast((event) => event.event_type.startsWith("run."));
  if (!latest) return { label: "尚未开始处理", tone: "warning" };

  const status = latest.event_type.slice(4);
  if (["started", "running", "resumed", "streaming"].includes(status)) {
    return { label: "正在处理", tone: "live" };
  }
  if (["waiting", "waiting_for_human", "paused", "blocked"].includes(status)) {
    return { label: "等待你决定", tone: "warning" };
  }
  if (["failed", "cancelled", "timed_out"].includes(status)) {
    return { label: "处理未完成", tone: "error" };
  }
  if (status === "completed") return { label: "处理已完成", tone: "live" };
  return { label: "处理状态已更新", tone: "warning" };
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

export function plainLanguageAgentMessage(content: string) {
  return content
    .replace(
      /本次执行停在\s+[a-z_]+，错误：[A-Z][A-Z0-9_]+。项目阶段没有被推进。/g,
      "本次处理没有完成，运行记录已经保留，项目仍停留在当前阶段。",
    )
    .replace(
      /上下文：Context v\d+；已批准主资源：[^。]+。/gi,
      "已提供资料：已确认的项目目标、用户和范围。",
    )
    .replace(
      /允许能力：[^；。\n]+；禁止动作：[^。\n]+。/g,
      "可以开展当前阶段的工作；不得读取密钥、越过项目范围或代替你确认阶段。",
    )
    .replace(
      /请只读取这份受控 Context Pack 开始工作；不要读取整段群聊、密钥或自行推进 Gate。/gi,
      "请基于这些资料开始工作。",
    )
    .replace(/Factory Lead/g, "主 Agent")
    .replace(/Reviewer/g, "审查 Agent")
    .replace(/Builder/g, "开发 Agent")
    .replace(/Context Pack/gi, "相关项目资料")
    .replace(/Context v\d+/gi, "相关项目资料")
    .replace(/Artifact DAG/gi, "产物区")
    .replace(/\bPermission\b/gi, "这一次允许")
    .replace(/\bGate\b/gi, "阶段确认")
    .replace(/\bRun\b/gi, "处理")
    .replace(/\bTask\b/gi, "任务")
    .replace(/\bAPI\b/g, "服务")
    .replace(/博查网络搜索/g, "网络搜索")
    .replace(/博查搜索/g, "网络搜索")
    .replace(/\bCAP-\d+\b/gi, "当前能力")
    .replace(
      /\b(?:waiting_human|partially_succeeded|succeeded|failed|cancelled|disconnected|stale)\b/gi,
      "当前状态",
    )
    .replace(/（[A-Z][A-Z0-9_]{2,}）/g, "")
    .replace(/\b[A-Z][A-Z0-9_]{2,}\b/g, "")
    .replace(/[，,]?\s*错误：\s*(?=[。；])/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}
