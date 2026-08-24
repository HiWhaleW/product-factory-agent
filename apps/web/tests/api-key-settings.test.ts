import { describe, expect, it } from "vitest";

import {
  credentialDeleteDisabled,
  credentialDraftError,
  credentialDraftFromStatus,
  credentialStatusMessage,
} from "../app/settings/api-key-settings";
import type { ProviderCredentialStatus } from "../lib/contracts";

const validDraft = {
  providerName: "DeepSeek",
  baseUrl: "https://api.deepseek.com",
  modelName: "deepseek-chat",
  apiKey: "test-key-12345678",
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
  });

  it("keeps every field empty when the current user has no saved credential", () => {
    const emptyStatus: ProviderCredentialStatus = {
      provider: "openai_compatible",
      configured: false,
      provider_name: null,
      base_url: null,
      model_name: null,
      masked_hint: null,
      updated_at: null,
      internal_test_fallback: false,
    };

    expect(credentialDraftFromStatus(emptyStatus)).toEqual({
      providerName: "",
      baseUrl: "",
      modelName: "",
      apiKey: "",
    });
  });

  it("only projects non-secret metadata for an existing user credential", () => {
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

    expect(credentialDraftFromStatus(configuredStatus)).toEqual({
      providerName: "My API",
      baseUrl: "https://models.example.com/v1",
      modelName: "my-model",
      apiKey: "",
    });
  });

  it("explains why an empty API Key cannot be added", () => {
    expect(credentialDraftError({ ...validDraft, apiKey: "" })).toBe(
      "请先粘贴 API Key，再点击添加。",
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
