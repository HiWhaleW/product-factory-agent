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

function payloadText(event: ProjectEvent, key: string) {
  const value = event.payload[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function payloadSummary(event: ProjectEvent) {
  return payloadText(event, "summary") || payloadText(event, "user_message");
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
