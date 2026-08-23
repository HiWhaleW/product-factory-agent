"use client";

import { FormEvent, useState } from "react";

import type { ApiError, ProviderCredentialStatus } from "@/lib/contracts";

const endpoint = "/api/control/api/v1/me/provider-credentials/model-api";

type CredentialDraft = {
  providerName: string;
  baseUrl: string;
  modelName: string;
  apiKey: string;
};

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

export function ApiKeySettings({ initialStatus }: { initialStatus: ProviderCredentialStatus }) {
  const [status, setStatus] = useState<ProviderCredentialStatus>(initialStatus);
  const [providerName, setProviderName] = useState(initialStatus.provider_name ?? "DeepSeek");
  const [baseUrl, setBaseUrl] = useState(initialStatus.base_url ?? "https://api.deepseek.com");
  const [modelName, setModelName] = useState(initialStatus.model_name ?? "deepseek-chat");
  const [apiKey, setApiKey] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState(initialStatus.configured
    ? `${initialStatus.provider_name ?? "模型接口"} · ${initialStatus.model_name ?? "已配置"} · ${initialStatus.masked_hint ?? ""}`
    : initialStatus.internal_test_fallback ? "当前仅使用内部测试 API" : "尚未添加 API Key");
  const [error, setError] = useState("");

  function applyStatus(next: ProviderCredentialStatus) {
    setStatus(next);
    if (next.provider_name) setProviderName(next.provider_name);
    if (next.base_url) setBaseUrl(next.base_url);
    if (next.model_name) setModelName(next.model_name);
    setMessage(next.configured
      ? `${next.provider_name ?? "模型接口"} · ${next.model_name ?? "已配置"} · ${next.masked_hint ?? ""}`
      : next.internal_test_fallback ? "当前仅使用内部测试 API" : "尚未添加 API Key");
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
        <div><p className="eyebrow">MODEL API / 模型接口</p><h2 id="api-key-title">自己的 API Key</h2></div>
        <span className={status?.configured ? "status-pill live" : "status-pill warning"}>{status?.configured ? "已配置" : "待配置"}</span>
      </header>
      <p className="api-key-explanation">
        支持使用 OpenAI 兼容接口的不同模型。Key 原文只发送到当前环境的受控后端，不会进入数据库、页面回包、日志、项目 Context 或 Artifact。
      </p>
      <form noValidate onSubmit={save}>
        <label htmlFor="provider-name"><strong>接口名称</strong><span>例如 DeepSeek、OpenAI 或你的模型服务</span></label>
        <input id="provider-name" maxLength={80} onChange={(event) => setProviderName(event.target.value)} required type="text" value={providerName} />
        <label htmlFor="provider-base-url"><strong>服务地址</strong><span>OpenAI 兼容 API 的 HTTPS Base URL</span></label>
        <input autoCapitalize="none" id="provider-base-url" maxLength={500} onChange={(event) => setBaseUrl(event.target.value)} required spellCheck={false} type="url" value={baseUrl} />
        <label htmlFor="provider-model"><strong>模型名</strong><span>填写接口服务实际支持的模型 ID</span></label>
        <input autoCapitalize="none" id="provider-model" maxLength={120} onChange={(event) => setModelName(event.target.value)} required spellCheck={false} type="text" value={modelName} />
        <label htmlFor="model-api-key"><strong>API Key</strong><span>{status?.configured ? "粘贴新 Key 以替换现有 Key" : "粘贴接口服务生成的 API Key"}</span></label>
        <input autoCapitalize="none" autoComplete="off" id="model-api-key" maxLength={512} minLength={8} onChange={(event) => setApiKey(event.target.value)} placeholder="••••••••••••" required spellCheck={false} type="password" value={apiKey} />
        <div className="api-key-actions">
          <button className="primary-button" disabled={pending} type="submit">{pending ? "处理中…" : status?.configured ? "替换 API Key" : "添加 API Key"}</button>
          {status?.configured
            ? <button className="danger-button" disabled={pending} onClick={remove} type="button">删除 API Key</button>
            : <span className="api-key-delete-empty">尚未保存用户 API Key，无需删除</span>}
        </div>
      </form>
      <div aria-live="polite" className="api-key-state"><span>{message}</span></div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {status?.internal_test_fallback ? <p className="internal-fallback-note">内部验证账号当前可使用本地测试 API；普通用户不会获得这项回退能力。</p> : null}
    </section>
  );
}
