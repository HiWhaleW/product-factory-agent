import { describe, expect, it } from "vitest";

import {
  codexCompatibilityClass,
  codexCompatibilityLabel,
} from "../app/settings/codex-runtime-settings";
import type { CodexRuntimeCapabilityStatus } from "../lib/contracts";

const baseStatus: CodexRuntimeCapabilityStatus = {
  runtime: "codex_app_server",
  configured: true,
  compatibility: "untested",
  config_version: "a".repeat(64),
  checked_at: null,
  checks: {
    app_server: false,
    responses_api: false,
    streaming: false,
    structured_output: false,
    tool_calling: false,
    secret_isolation: false,
  },
  error_code: null,
  user_message: "尚未检测",
};

describe("Codex runtime compatibility projection", () => {
  it("keeps an unconfigured account out of compatibility testing", () => {
    const status = {
      ...baseStatus,
      configured: false,
      compatibility: "not_configured" as const,
    };
    expect(codexCompatibilityLabel(status)).toBe("等待 API 配置");
    expect(codexCompatibilityClass(status)).toBe("status-pill warning");
  });

  it("distinguishes compatible and incompatible results", () => {
    expect(
      codexCompatibilityLabel({ ...baseStatus, compatibility: "compatible" }),
    ).toBe("兼容性通过");
    expect(
      codexCompatibilityClass({ ...baseStatus, compatibility: "compatible" }),
    ).toBe("status-pill live");
    expect(
      codexCompatibilityClass({ ...baseStatus, compatibility: "incompatible" }),
    ).toBe("status-pill error");
  });
});
