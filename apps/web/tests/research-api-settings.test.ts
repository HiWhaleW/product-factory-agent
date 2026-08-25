import { describe, expect, it } from "vitest";

import { researchCredentialError } from "../app/settings/research-api-settings";

describe("researchCredentialError", () => {
  it("accepts a user-provided public HTTPS service and a valid key", () => {
    expect(researchCredentialError(
      "自选搜索厂商",
      "https://search.example.com/v1",
      "search-test-key-1234",
    )).toBe("");
  });

  it("keeps every field required and rejects HTTP", () => {
    expect(researchCredentialError(
      "",
      "https://search.example.com/v1",
      "search-test-key-1234",
    )).toContain("厂商");
    expect(researchCredentialError(
      "自选搜索厂商",
      "http://api.bochaai.com/v1",
      "bocha-test-key-1234",
    )).toContain("HTTPS");
    expect(researchCredentialError(
      "自选搜索厂商",
      "https://search.example.com/v1",
      "",
    )).toContain("粘贴");
  });
});
