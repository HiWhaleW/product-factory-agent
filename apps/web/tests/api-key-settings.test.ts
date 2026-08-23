import { describe, expect, it } from "vitest";

import { credentialDraftError } from "../app/settings/api-key-settings";

const validDraft = {
  providerName: "DeepSeek",
  baseUrl: "https://api.deepseek.com",
  modelName: "deepseek-chat",
  apiKey: "test-key-12345678",
};

describe("credentialDraftError", () => {
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
