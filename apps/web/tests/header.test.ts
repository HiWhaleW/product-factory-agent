import { describe, expect, it } from "vitest";

import type { SessionStatus } from "../lib/contracts";
import { identityPresentation, nextHeaderPopover } from "../lib/header";

function session(overrides: Partial<SessionStatus> = {}): SessionStatus {
  return {
    authenticated: true,
    user_id: "user-1",
    display_name: "测试用户",
    role: "user",
    expires_at: "2026-08-24T12:00:00Z",
    reason: "active",
    auth_enforced: true,
    ...overrides,
  };
}

describe("identityPresentation", () => {
  it("只暴露用户需要的名称、账号身份和登录状态", () => {
    expect(identityPresentation(session())).toEqual({
      displayName: "测试用户",
      accountLabel: "种子用户",
      loginLabel: "已登录",
    });
  });

  it("区分内部管理员与未登录访客", () => {
    expect(identityPresentation(session({ role: "admin" })).accountLabel).toBe("管理员账号");
    expect(identityPresentation(session({ authenticated: false, display_name: null, role: null }))).toEqual({
      displayName: "访客",
      accountLabel: "访客",
      loginLabel: "需要登录",
    });
  });
});

describe("nextHeaderPopover", () => {
  it("在同一入口上切换关闭，并在两个入口间切换", () => {
    expect(nextHeaderPopover(null, "identity")).toBe("identity");
    expect(nextHeaderPopover("identity", "identity")).toBeNull();
    expect(nextHeaderPopover("identity", "notifications")).toBe("notifications");
  });
});
