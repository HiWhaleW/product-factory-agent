import { EventType } from "@ag-ui/core";
import { describe, expect, it } from "vitest";

import { eventStreamSync, parseAgUiProjectEvent } from "../lib/ag-ui-events";

const persistedEvent = {
  id: "event-1",
  project_id: "project-1",
  sequence: 17,
  event_type: "artifact.created",
  payload: { artifact_id: "artifact-1" },
  created_at: "2026-08-23T00:00:00Z",
};

describe("AG-UI event transport", () => {
  it("uses AG-UI SSE as the primary transport and polling only as fallback", () => {
    expect(eventStreamSync).toEqual({
      transport: "ag-ui-sse",
      fallbackIntervalMs: 2500,
    });
  });

  it("unwraps a valid AG-UI custom event into the persisted project event", () => {
    expect(parseAgUiProjectEvent(JSON.stringify({
      type: EventType.CUSTOM,
      name: persistedEvent.event_type,
      value: persistedEvent,
    }))).toEqual(persistedEvent);
  });

  it("fails closed for malformed, mismatched, or unknown event envelopes", () => {
    expect(parseAgUiProjectEvent("not json")).toBeNull();
    expect(parseAgUiProjectEvent(JSON.stringify({
      type: EventType.CUSTOM,
      name: "gate.decided",
      value: persistedEvent,
    }))).toBeNull();
    expect(parseAgUiProjectEvent(JSON.stringify({ type: "UNKNOWN" }))).toBeNull();
  });
});
