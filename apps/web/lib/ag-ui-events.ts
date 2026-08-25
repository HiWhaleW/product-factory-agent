import { CustomEventSchema, EventType } from "@ag-ui/core";

import type { ProjectEvent } from "@/lib/contracts";

export const eventStreamSync = {
  transport: "ag-ui-sse",
  fallbackIntervalMs: 2500,
} as const;

function isProjectEvent(value: unknown): value is ProjectEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<ProjectEvent>;
  return (
    typeof event.id === "string"
    && typeof event.project_id === "string"
    && typeof event.sequence === "number"
    && Number.isInteger(event.sequence)
    && event.sequence > 0
    && typeof event.event_type === "string"
    && Boolean(event.payload)
    && typeof event.payload === "object"
    && typeof event.created_at === "string"
  );
}

export function parseAgUiProjectEvent(data: string): ProjectEvent | null {
  let candidate: unknown;
  try {
    candidate = JSON.parse(data);
  } catch {
    return null;
  }
  const parsed = CustomEventSchema.safeParse(candidate);
  if (!parsed.success || parsed.data.type !== EventType.CUSTOM) return null;
  if (!isProjectEvent(parsed.data.value)) return null;
  if (parsed.data.name !== parsed.data.value.event_type) return null;
  return parsed.data.value;
}
