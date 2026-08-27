import { describe, expect, it } from "vitest";

import {
  credentialDeleteDisabled,
  credentialCanConfirmSavedStatus,
  credentialConfirmationDisabled,
  credentialConfirmationLabel,
  credentialDraftError,
  emptyCredentialDraft,
  credentialStatusMessage,
} from "../app/settings/api-key-settings";
import type {
  CodexRuntimeCapabilityStatus,
  ProviderCredentialStatus,
} from "../lib/contracts";

const validDraft = {
  providerName: "DeepSeek",
  baseUrl: "https://api.deepseek.com",
  modelName: "deepseek-chat",
  apiKey: "test-key-12345678",
};

const compatibleStatus: CodexRuntimeCapabilityStatus = {
  runtime: "codex_app_server",
  configured: true,
  compatibility: "compatible",
  config_version: "a".repeat(64),
  checked_at: "2026-08-28T00:00:00Z",
  checks: {
    app_server: true,
    responses_api: true,
    streaming: true,
    structured_output: true,
    tool_calling: true,
    secret_isolation: true,
  },
  error_code: null,
  user_message: "API 已确认。",
};

describe("credentialDraftError", () => {
  it("shows a disabled delete action without exposing the internal fallback", () => {
    const fallbackStatus: ProviderCredentialStatus = {
      provider: "openai_compatible",
      configured: false,
      provider_name: null,
      base_url: null,
      model_name: null,
      masked_hint: null,
      updated_at: null,
      internal_test_fallback: true,
    };

    expect(credentialDeleteDisabled(fallbackStatus, false)).toBe(true);
    expect(credentialStatusMessage(fallbackStatus)).toBe("尚未添加 API Key");
    expect(credentialStatusMessage(fallbackStatus)).not.toContain("内部测试");
  });

  it("enables delete only for a saved user credential while idle", () => {
    const configuredStatus: ProviderCredentialStatus = {
      provider: "openai_compatible",
      configured: true,
      provider_name: "My API",
      base_url: "https://models.example.com/v1",
      model_name: "my-model",
      masked_hint: "••••5678",
      updated_at: "2026-08-24T00:00:00Z",
      internal_test_fallback: false,
    };

    expect(credentialDeleteDisabled(configuredStatus, false)).toBe(false);
    expect(credentialDeleteDisabled(configuredStatus, true)).toBe(true);
    const savedDraft = emptyCredentialDraft();
    expect(credentialCanConfirmSavedStatus(configuredStatus, savedDraft)).toBe(true);
    expect(credentialConfirmationDisabled(configuredStatus, savedDraft, false)).toBe(false);
    expect(credentialConfirmationLabel(configuredStatus, compatibleStatus)).toBe("已确认");
    expect(
      credentialConfirmationDisabled(
        configuredStatus,
        { ...savedDraft, modelName: "unsaved-model" },
        false,
      ),
    ).toBe(true);
  });

  it("keeps every replacement field empty for the current user", () => {
    expect(emptyCredentialDraft()).toEqual({
      providerName: "",
      baseUrl: "",
      modelName: "",
      apiKey: "",
    });
  });

  it("explains why an empty API Key cannot be added", () => {
    expect(credentialDraftError({ ...validDraft, apiKey: "" })).toBe(
      "请先粘贴 API Key，再点击保存。",
    );
  });

  it("rejects non-HTTPS endpoints and whitespace in keys", () => {
    expect(credentialDraftError({ ...validDraft, baseUrl: "http://models.example.com" })).toContain(
      "HTTPS",
    );
    expect(credentialDraftError({ ...validDraft, apiKey: "test key" })).toBe(
      "API Key 不能包含空格或换行。",
    );
  });

  it("accepts a complete OpenAI-compatible credential draft", () => {
    expect(credentialDraftError(validDraft)).toBe("");
  });
});
