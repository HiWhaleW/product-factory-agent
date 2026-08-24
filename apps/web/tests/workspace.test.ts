import { describe, expect, it } from "vitest";

import type { ArtifactNode, ProjectEvent } from "../lib/contracts";
import {
  agentIntroduction,
  artifactVersionOptions,
  composeReferencedMessage,
  eventPresentation,
  friendlyProcessStep,
  formatProjectVersion,
  groupProcessEventsForConversation,
  isChatMilestoneEvent,
  parseReferencedMessage,
  stageStartEventId,
  visibleRunState,
} from "../lib/workspace";

const artifact: ArtifactNode = {
  id: "artifact-1",
  kind: "markdown",
  latest_version: 3,
  stage: "prd",
  status: "waiting_review",
  title: "产品需求文档",
  owner_agent: "ai-pm",
  created_at: "2026-08-21T00:00:00Z",
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
  it("offers every persisted artifact version from newest to oldest", () => {
    expect(artifactVersionOptions(3)).toEqual([3, 2, 1]);
    expect(artifactVersionOptions(1)).toEqual([1]);
  });

  it("formats the project-level context version for the workspace title", () => {
    expect(formatProjectVersion(1)).toBe("V1.0");
    expect(formatProjectVersion(3)).toBe("V3.0");
  });

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

  it("derives truthful self-introductions only from persisted join events", () => {
    expect(agentIntroduction(projectEvent("agent.joined", { agent_id: "builder" }))).toMatchObject({
      profile: { label: "Builder" },
    });
    expect(agentIntroduction(projectEvent("run.completed", { agent_id: "builder" }))).toBeNull();
    expect(agentIntroduction(projectEvent("agent.joined", { agent_id: "unknown-agent" }))).toBeNull();
  });

  it("keeps the real lead invitation attached to each persisted agent join", () => {
    const introduction = agentIntroduction(projectEvent("agent.joined", { agent_name: "Reviewer" }));
    expect(introduction).toMatchObject({
      profile: { id: "reviewer", label: "Reviewer" },
      text: expect.stringContaining("@Reviewer"),
    });
  });

  it("splits execution records at message and stage boundaries", () => {
    const events = [
      { ...projectEvent("project.created"), sequence: 1 },
      { ...projectEvent("message.created"), id: "user-message", sequence: 2 },
      { ...projectEvent("run.started", { agent_id: "factory-lead", run_id: "run-1" }), id: "lead-start", sequence: 3 },
      { ...projectEvent("run.completed", { run_id: "run-1" }), id: "lead-done", sequence: 4 },
      { ...projectEvent("message.created", { run_id: "run-1" }), id: "lead-message", sequence: 5 },
      { ...projectEvent("clarification.recorded", { run_id: "run-1" }), id: "clarification", sequence: 6 },
      { ...projectEvent("message.created"), id: "second-user-message", sequence: 7 },
      { ...projectEvent("run.started", { agent_id: "factory-lead", run_id: "run-2" }), id: "second-start", sequence: 8 },
      { ...projectEvent("run.completed", { run_id: "run-2" }), id: "second-done", sequence: 9 },
      { ...projectEvent("message.created"), id: "second-lead-message", sequence: 10 },
      { ...projectEvent("project.state_changed", { state: "mrd" }), id: "mrd-start", sequence: 11 },
      { ...projectEvent("tool_run.started", { tool_id: "web_research" }), id: "mrd-tool", sequence: 12 },
    ];

    expect(groupProcessEventsForConversation(events).map((group) => ({
      ids: group.events.map((event) => event.id),
      label: group.label,
      state: group.state,
    }))).toEqual([
      { ids: ["lead-start", "lead-done", "clarification"], label: "项目对齐", state: "alignment" },
      { ids: ["second-start", "second-done"], label: "项目对齐", state: "alignment" },
      { ids: ["mrd-tool"], label: "MRD", state: "mrd" },
    ]);
  });

  it("translates technical events into plain-language process steps", () => {
    expect(friendlyProcessStep(projectEvent("context.pack_created", {
      recipient_agent_id: "factory-lead",
    }))).toEqual({
      label: "准备资料",
      summary: "已准备好本次任务需要的项目信息。接下来由 主 Agent 处理。",
    });
    expect(friendlyProcessStep(projectEvent("tool_run.started", {
      tool_id: "web_research",
    }))).toEqual({
      label: "调用网络搜索工具：博查",
      summary: "网络搜索工具：博查正在执行。",
    });
    expect(friendlyProcessStep(projectEvent("tool_run.started", {
      tool_id: "codex_cli",
    }))).toMatchObject({ label: "调用代码实现工具：Codex" });
    expect(friendlyProcessStep(projectEvent("tool_run.recovered", {
      tool_id: "web_research",
    }))).toMatchObject({ label: "调用网络搜索工具：博查" });
  });

  it("finds the beginning of a completed visible stage", () => {
    const events = [
      projectEvent("project.created"),
      { ...projectEvent("project.state_changed", { state: "mrd" }), id: "mrd-start", sequence: 2 },
      { ...projectEvent("project.state_changed", { state: "development_backend" }), id: "development-start", sequence: 3 },
      { ...projectEvent("project.state_changed", { state: "development_frontend" }), id: "frontend-start", sequence: 4 },
    ];
    expect(stageStartEventId(events, ["alignment"])).toBe("project.created");
    expect(stageStartEventId(events, ["mrd"])).toBe("mrd-start");
    expect(stageStartEventId(events, ["development_backend", "development_frontend"])).toBe("development-start");
  });

  it("keeps only stage changes and real agent joins prominent in chat", () => {
    expect(isChatMilestoneEvent(projectEvent("project.state_changed"))).toBe(true);
    expect(isChatMilestoneEvent(projectEvent("agent.joined"))).toBe(true);
    expect(isChatMilestoneEvent(projectEvent("tool_run.completed"))).toBe(false);
    expect(isChatMilestoneEvent(projectEvent("artifact.created"))).toBe(false);
  });
});
