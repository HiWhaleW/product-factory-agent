import { describe, expect, it } from "vitest";

import type { ArtifactNode, ProjectEvent } from "../lib/contracts";
import {
  composeReferencedMessage,
  eventPresentation,
  parseReferencedMessage,
  visibleRunState,
} from "../lib/workspace";

const artifact: ArtifactNode = {
  id: "artifact-1",
  kind: "markdown",
  latest_version: 3,
  stage: "prd",
  status: "waiting_review",
  title: "产品需求文档",
};

function projectEvent(eventType: string, payload: Record<string, unknown> = {}): ProjectEvent {
  return {
    created_at: "2026-08-21T00:00:00Z",
    event_type: eventType,
    id: eventType,
    payload,
    project_id: "project-1",
    sequence: 1,
  };
}

describe("workspace projection helpers", () => {
  it("persists a visible artifact reference with the message", () => {
    expect(composeReferencedMessage("请检查边界", artifact)).toBe(
      "【引用产物｜产品需求文档｜v3｜artifact:artifact-1】\n请检查边界",
    );
  });

  it("separates persisted artifact identity from user-facing message copy", () => {
    expect(parseReferencedMessage(
      "【引用产物｜产品需求文档｜v3｜artifact:artifact-1】\n请检查边界",
    )).toEqual({
      body: "请检查边界",
      reference: { artifactId: "artifact-1", title: "产品需求文档", version: 3 },
    });
    expect(parseReferencedMessage("普通消息")).toEqual({ body: "普通消息", reference: null });
  });

  it("derives the latest visible run state without inventing one", () => {
    expect(visibleRunState([])).toEqual({ label: "Agent 未接入", tone: "warning" });
    expect(visibleRunState([projectEvent("run.started"), projectEvent("run.waiting_for_human")])).toEqual({
      label: "Run 等待用户",
      tone: "warning",
    });
  });

  it("uses safe summaries for known and unknown events", () => {
    expect(eventPresentation(projectEvent("agent.joined", { agent_name: "AI PM" }))).toMatchObject({
      label: "Agent 入群",
      tone: "agent",
    });
    expect(eventPresentation(projectEvent("custom.event"))).toEqual({
      label: "custom.event",
      summary: "控制面事件 #1",
      tone: "unknown",
    });
    expect(eventPresentation(projectEvent("project.state_changed", {
      state: "development_backend",
    }))).toMatchObject({ summary: "项目阶段已更新为 后端开发。" });
  });
});
