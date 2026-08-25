"use client";

import { FormEvent, useState } from "react";

import type { ApiError, ResearchCredentialStatus } from "@/lib/contracts";

const endpoint = "/api/control/api/v1/me/provider-credentials/web-search";

export function researchCredentialError(
  providerName: string,
  baseUrl: string,
  apiKey: string,
): string {
  if (!providerName.trim()) return "请填写 API 厂商。";
  if (!baseUrl.trim()) return "请填写服务地址。";
  try {
    const parsed = new URL(baseUrl.trim());
    if (parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password) {
      return "服务地址必须是公开可访问的 HTTPS Base URL。";
    }
  } catch {
    return "服务地址必须是有效的 HTTPS Base URL。";
  }
  if (!apiKey) return "请先粘贴 API Key，再点击添加。";
  if (apiKey !== apiKey.trim() || /\s/.test(apiKey)) {
    return "API Key 不能包含空格或换行。";
  }
  if (apiKey.length < 8 || apiKey.length > 512) {
    return "API Key 长度需为 8–512 个字符。";
  }
  return "";
}

export function ResearchApiSettings({ initialStatus }: { initialStatus: ResearchCredentialStatus }) {
  const [status, setStatus] = useState(initialStatus);
  const [providerName, setProviderName] = useState(initialStatus.provider_name ?? "");
  const [baseUrl, setBaseUrl] = useState(initialStatus.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState(
    initialStatus.configured
      ? `${initialStatus.provider_name ?? "网络搜索"} · ${initialStatus.masked_hint ?? "已配置"}`
      : "尚未添加网络搜索 API",
  );
  const [error, setError] = useState("");

  function applyStatus(next: ResearchCredentialStatus) {
    setStatus(next);
    setProviderName(next.provider_name ?? "");
    setBaseUrl(next.base_url ?? "");
    setApiKey("");
    setMessage(next.configured
      ? `${next.provider_name ?? "网络搜索"} · ${next.masked_hint ?? "已配置"}`
      : "尚未添加网络搜索 API");
    window.dispatchEvent(new CustomEvent("product-factory:provider-credential-changed"));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = researchCredentialError(providerName, baseUrl, apiKey);
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
        body: JSON.stringify({ provider_name: providerName, base_url: baseUrl, api_key: apiKey }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error?.user_message ?? "网络搜索 API 保存失败");
      }
      applyStatus((await response.json()) as ResearchCredentialStatus);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "网络搜索 API 保存失败");
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    if (!window.confirm("确认删除你保存的网络搜索 API？删除后 Agent 将无法进行网络搜索。")) return;
    setPending(true);
    setError("");
    try {
      const response = await fetch(endpoint, { method: "DELETE" });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error?.user_message ?? "网络搜索 API 删除失败");
      }
      applyStatus((await response.json()) as ResearchCredentialStatus);
      setMessage("已删除网络搜索 API");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "网络搜索 API 删除失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="research-api-title" className="api-key-settings">
      <header>
        <div><p className="eyebrow">WEB SEARCH / 网络搜索</p><h2 id="research-api-title">网络搜索 API</h2></div>
        <span className={status.configured ? "status-pill live" : "status-pill warning"}>{status.configured ? "已配置" : "待配置"}</span>
      </header>
      <p className="api-key-explanation">
        产品不提供搜索额度，请填写你自己的网络搜索服务。Key 原文不会进入数据库、页面回包、日志或项目资料。不同厂商的调用方式不同，保存后页面会明确标记当前是否已能用于项目。
      </p>
      <form autoComplete="off" noValidate onSubmit={save}>
        <label htmlFor="research-provider"><strong>API 厂商</strong><span>填写你使用的网络搜索服务</span></label>
        <input id="research-provider" maxLength={80} onChange={(event) => setProviderName(event.target.value)} required type="text" value={providerName} />
        <label htmlFor="research-base-url"><strong>服务地址</strong><span>该厂商提供的 HTTPS Base URL</span></label>
        <input autoCapitalize="none" id="research-base-url" maxLength={500} onChange={(event) => setBaseUrl(event.target.value)} required spellCheck={false} type="url" value={baseUrl} />
        <label htmlFor="research-api-key"><strong>API Key</strong><span>{status.configured ? "粘贴新 Key 以替换现有 Key" : "粘贴该厂商生成的 API Key"}</span></label>
        <input autoCapitalize="none" autoComplete="new-password" id="research-api-key" maxLength={512} minLength={8} name="research-api-key" onChange={(event) => setApiKey(event.target.value)} required spellCheck={false} type="password" value={apiKey} />
        <div className="api-key-actions">
          <button className="primary-button" disabled={pending} type="submit">{pending ? "处理中…" : status.configured ? "替换 API Key" : "添加 API Key"}</button>
          <button className="danger-button" disabled={pending || !status.configured} onClick={remove} type="button">删除 API Key</button>
        </div>
      </form>
      <div aria-live="polite" className="api-key-state"><span>{message}</span></div>
      {status.configured && !status.runtime_supported ? (
        <p className="form-error" role="status">这份配置已保存，但当前版本还不能直接使用该厂商进行搜索。</p>
      ) : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </section>
  );
}
