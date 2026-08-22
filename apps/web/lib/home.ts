import type { GateRequest, PermissionRequest, Project } from "./contracts";
import { projectStageLabel } from "./stages";

export type AttentionItem = {
  id: string;
  kind: "gate" | "permission";
  label: string;
  createdAt: string;
};

export type ProjectAttention = {
  projectId: string;
  items: AttentionItem[];
  unavailable: boolean;
};

export type ProjectFilter = "active" | "waiting" | "paused" | "completed";

export function projectAttention(
  projectId: string,
  gates: GateRequest[],
  permissions: PermissionRequest[],
): ProjectAttention {
  const items: AttentionItem[] = [
    ...gates
      .filter((gate) => gate.status === "open")
      .map((gate) => ({
        id: gate.id,
        kind: "gate" as const,
        label: `${gate.gate_type} 产品决策`,
        createdAt: gate.opened_at,
      })),
    ...permissions
      .filter((permission) => permission.status === "open")
      .map((permission) => ({
        id: permission.id,
        kind: "permission" as const,
        label: `${permission.tool_name} 工具权限`,
        createdAt: permission.created_at,
      })),
  ].sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  return { projectId, items, unavailable: false };
}

export function projectFilter(project: Project, attention: ProjectAttention): ProjectFilter {
  if (attention.items.length > 0) return "waiting";
  if (["paused", "killed"].includes(project.state)) return "paused";
  if (["completed", "archived"].includes(project.state)) return "completed";
  return "active";
}

export function projectNextAction(project: Project, attention: ProjectAttention) {
  const gate = attention.items.find((item) => item.kind === "gate");
  if (gate) return `决定 ${gate.label}`;
  const permission = attention.items.find((item) => item.kind === "permission");
  if (permission) return `处理 ${permission.label}`;
  if (attention.unavailable) return "待重新读取控制面状态";
  if (project.state === "alignment") return "继续项目对齐";
  return `继续${projectStageLabel(project.state)}`;
}

export function formatProjectActivity(isoDate: string) {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(date);
}
