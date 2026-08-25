"use client";

import { FormEvent, useState } from "react";

import type { ApiError, ProviderCredentialStatus } from "@/lib/contracts";

const endpoint = "/api/control/api/v1/me/provider-credentials/model-api";

export type CredentialDraft = {
  providerName: string;
  baseUrl: string;
  modelName: string;
  apiKey: string;
};

export function credentialDraftFromStatus(
  status: ProviderCredentialStatus,
): CredentialDraft {
  return {
    providerName: status.configured ? status.provider_name ?? "" : "",
    baseUrl: status.configured ? status.base_url ?? "" : "",
    modelName: status.configured ? status.model_name ?? "" : "",
    apiKey: "",
  };
}

export function credentialDraftError(draft: CredentialDraft): string {
  if (!draft.providerName.trim()) return "请填写接口名称。";
  if (!draft.baseUrl.trim()) return "请填写服务地址。";
  try {
    const parsed = new URL(draft.baseUrl.trim());
    if (parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password) {
      return "服务地址必须是公开可访问的 HTTPS Base URL。";
    }
  } catch {
    return "服务地址必须是有效的 HTTPS Base URL。";
  }
  if (!draft.modelName.trim()) return "请填写模型名。";
  if (!draft.apiKey) return "请先粘贴 API Key，再点击添加。";
  if (draft.apiKey !== draft.apiKey.trim() || /\s/.test(draft.apiKey)) {
    return "API Key 不能包含空格或换行。";
  }
  if (draft.apiKey.length < 8 || draft.apiKey.length > 512) {
    return "API Key 长度需为 8–512 个字符。";
  }
  return "";
}

export function credentialStatusMessage(status: ProviderCredentialStatus): string {
  return status.configured
    ? `${status.provider_name ?? "模型接口"} · ${status.model_name ?? "已配置"} · ${status.masked_hint ?? ""}`
    : "尚未添加 API Key";
}

export function credentialDeleteDisabled(
  status: ProviderCredentialStatus,
  pending: boolean,
): boolean {
  return pending || !status.configured;
}

export function ApiKeySettings({ initialStatus }: { initialStatus: ProviderCredentialStatus }) {
  const initialDraft = credentialDraftFromStatus(initialStatus);
  const [status, setStatus] = useState<ProviderCredentialStatus>(initialStatus);
  const [providerName, setProviderName] = useState(initialDraft.providerName);
  const [baseUrl, setBaseUrl] = useState(initialDraft.baseUrl);
  const [modelName, setModelName] = useState(initialDraft.modelName);
  const [apiKey, setApiKey] = useState(initialDraft.apiKey);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState(credentialStatusMessage(initialStatus));
  const [error, setError] = useState("");

  function applyStatus(next: ProviderCredentialStatus) {
    const nextDraft = credentialDraftFromStatus(next);
    setStatus(next);
    setProviderName(nextDraft.providerName);
    setBaseUrl(nextDraft.baseUrl);
    setModelName(nextDraft.modelName);
    setApiKey(nextDraft.apiKey);
    setMessage(credentialStatusMessage(next));
    window.dispatchEvent(new CustomEvent("product-factory:provider-credential-changed"));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = credentialDraftError({ providerName, baseUrl, modelName, apiKey });
    if (validationError) {
      setError(validationError);
      return;
    }
    setPending(true);
    setError("");
    try {
      const response = await fetch(endpoint, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          provider_name: providerName,
          base_url: baseUrl,
          model_name: modelName,
          api_key: apiKey,
        }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error?.user_message ?? "API Key 保存失败");
      }
      applyStatus((await response.json()) as ProviderCredentialStatus);
      setApiKey("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "API Key 保存失败");
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    if (!window.confirm("确认删除你保存的 API Key？删除后 Agent 将无法使用该接口执行任务。")) return;
    setPending(true);
    setError("");
    try {
      const response = await fetch(endpoint, { method: "DELETE" });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error?.user_message ?? "API Key 删除失败");
      }
      applyStatus((await response.json()) as ProviderCredentialStatus);
      setMessage("已删除 API Key");
      setApiKey("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "API Key 删除失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="api-key-title" className="api-key-settings">
      <header>
        <div><p className="eyebrow">MODEL API / 模型接口</p><h2 id="api-key-title">大模型 API</h2></div>
        <span className={status?.configured ? "status-pill live" : "status-pill warning"}>{status?.configured ? "已配置" : "待配置"}</span>
      </header>
      <p className="api-key-explanation">
        支持使用 OpenAI 兼容接口的不同模型。Key 原文只发送到当前环境的受控后端，不会进入数据库、页面回包、日志、项目 Context 或 Artifact。
      </p>
      <form autoComplete="off" noValidate onSubmit={save}>
        <label htmlFor="provider-name"><strong>接口名称</strong><span>例如 DeepSeek、OpenAI 或你的模型服务</span></label>
        <input id="provider-name" maxLength={80} onChange={(event) => setProviderName(event.target.value)} required type="text" value={providerName} />
        <label htmlFor="provider-base-url"><strong>服务地址</strong><span>OpenAI 兼容 API 的 HTTPS Base URL</span></label>
        <input autoCapitalize="none" id="provider-base-url" maxLength={500} onChange={(event) => setBaseUrl(event.target.value)} required spellCheck={false} type="url" value={baseUrl} />
        <label htmlFor="provider-model"><strong>模型名</strong><span>填写接口服务实际支持的模型 ID</span></label>
        <input autoCapitalize="none" id="provider-model" maxLength={120} onChange={(event) => setModelName(event.target.value)} required spellCheck={false} type="text" value={modelName} />
        <label htmlFor="model-api-key"><strong>API Key</strong><span>{status?.configured ? "粘贴新 Key 以替换现有 Key" : "粘贴接口服务生成的 API Key"}</span></label>
        <input autoCapitalize="none" autoComplete="new-password" id="model-api-key" maxLength={512} minLength={8} name="model-api-key" onChange={(event) => setApiKey(event.target.value)} required spellCheck={false} type="password" value={apiKey} />
        <div className="api-key-actions">
          <button className="primary-button" disabled={pending} type="submit">{pending ? "处理中…" : status?.configured ? "替换 API Key" : "添加 API Key"}</button>
          <button
            className="danger-button"
            disabled={credentialDeleteDisabled(status, pending)}
            onClick={remove}
            type="button"
          >删除 API Key</button>
        </div>
      </form>
      <div aria-live="polite" className="api-key-state"><span>{message}</span></div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </section>
  );
}
