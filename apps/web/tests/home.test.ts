import { describe, expect, it } from "vitest";

import type { GateRequest, PermissionRequest, Project } from "../lib/contracts";
import { nextHeaderPopover } from "../lib/header";
import {
  formatProjectActivity,
  projectAttention,
  projectFilter,
  projectNextAction,
} from "../lib/home";
import {
  onboardingAllowed,
  onboardingSteps,
  onboardingStorageKey,
  shouldAutoOpenOnboarding,
} from "../lib/onboarding";

const project: Project = {
  id: "project-1",
  owner_user_id: "local-admin",
  name: "真实项目",
  state: "alignment",
  context_version: 1,
  iteration_version: 1,
  created_at: "2026-08-21T08:00:00Z",
  updated_at: "2026-08-21T08:09:00Z",
};

const gate: GateRequest = {
  id: "gate-1",
  project_id: project.id,
  gate_type: "G0",
  context_version: 1,
  status: "open",
  target_state: "mrd",
  reason: "项目对齐已完成，等待用户决定。",
  impacted_artifact_refs: [],
  known_issues: [],
  opened_at: "2026-08-21T08:10:00Z",
};

const permission: PermissionRequest = {
  id: "permission-1",
  project_id: project.id,
  task_id: "task-1",
  run_id: "run-1",
  tool_name: "bocha_search",
  input_hash: "hash",
  risk_level: "medium",
  reason: "公开搜索需要一次性计费授权。",
  redacted_parameters: { query_sha256: "hash" },
  context_version: 1,
  status: "decided",
  expires_at: null,
  created_at: "2026-08-21T08:11:00Z",
};

describe("home project projections", () => {
  it("keeps the header menus mutually exclusive and toggles the active menu closed", () => {
    expect(nextHeaderPopover(null, "notifications")).toBe("notifications");
    expect(nextHeaderPopover("notifications", "identity")).toBe("identity");
    expect(nextHeaderPopover("identity", "identity")).toBeNull();
  });

  it("only counts real open Gate and Permission requests", () => {
    const attention = projectAttention(project.id, [gate], [permission]);
    expect(attention.items).toEqual([
      expect.objectContaining({ id: "gate-1", kind: "gate", label: "G0 产品决策" }),
    ]);
    expect(projectFilter(project, attention)).toBe("waiting");
    expect(projectNextAction(project, attention)).toBe("决定 G0 产品决策");
  });

  it("keeps an ordinary alignment project active without inventing attention", () => {
    const attention = projectAttention(project.id, [], []);
    expect(projectFilter(project, attention)).toBe("active");
    expect(projectNextAction(project, attention)).toBe("继续项目对齐");
  });

  it("formats real activity timestamps in the product timezone", () => {
    expect(formatProjectActivity(project.updated_at)).toMatch(/08.*21.*16.*09/);
  });

  it("never opens onboarding over an enforced unauthenticated login page", () => {
    const loggedOut = { auth_enforced: true, authenticated: false };
    const loggedIn = { auth_enforced: true, authenticated: true };

    expect(onboardingAllowed(loggedOut)).toBe(false);
    expect(shouldAutoOpenOnboarding(loggedOut, "/", false)).toBe(false);
    expect(shouldAutoOpenOnboarding(loggedIn, "/", false)).toBe(true);
    expect(shouldAutoOpenOnboarding(loggedIn, "/", true)).toBe(false);
  });

  it("tracks onboarding completion independently for each real user", () => {
    expect(onboardingStorageKey("user-a")).toBe("product-factory:onboarding:v2:user-a");
    expect(onboardingStorageKey("user-b")).toBe("product-factory:onboarding:v2:user-b");
    expect(onboardingStorageKey("user-a")).not.toBe(onboardingStorageKey("user-b"));
  });

  it("guides first-time users to configure their own API key", () => {
    expect(onboardingSteps).toHaveLength(5);
    expect(onboardingSteps[1]).toMatchObject({
      title: "先连接你的 AI",
      settingsLink: true,
    });
    expect(onboardingSteps[1].body).toContain("专属于你的 API Key");
  });
});
