"use client";

import { useEffect, useState } from "react";

import type { ApiError, CodexRuntimeCapabilityStatus } from "@/lib/contracts";

const statusEndpoint = "/api/control/api/v1/me/codex-runtime";
const checkEndpoint = "/api/control/api/v1/me/codex-runtime/compatibility";

export function codexCompatibilityLabel(status: CodexRuntimeCapabilityStatus): string {
  if (!status.configured) return "等待 API 配置";
  if (status.compatibility === "compatible") return "兼容性通过";
  if (status.compatibility === "partial") return "部分兼容";
  if (status.compatibility === "incompatible") return "检测未通过";
  return "等待检测";
}

export function codexCompatibilityClass(status: CodexRuntimeCapabilityStatus): string {
  if (status.compatibility === "compatible") return "status-pill live";
  if (status.compatibility === "incompatible") return "status-pill error";
  return "status-pill warning";
}

export function CodexRuntimeSettings({
  initialStatus,
}: {
  initialStatus: CodexRuntimeCapabilityStatus;
}) {
  const [status, setStatus] = useState(initialStatus);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function refresh() {
      const response = await fetch(statusEndpoint, { cache: "no-store" });
      if (response.ok) setStatus((await response.json()) as CodexRuntimeCapabilityStatus);
    }
    function refreshFromCredentialChange() {
      void refresh();
    }
    function refreshFromConfirmation(event: Event) {
      const confirmationEvent = event as CustomEvent<CodexRuntimeCapabilityStatus>;
      setStatus(confirmationEvent.detail);
    }
    window.addEventListener(
      "product-factory:provider-credential-changed",
      refreshFromCredentialChange,
    );
    window.addEventListener(
      "product-factory:codex-runtime-confirmed",
      refreshFromConfirmation,
    );
    return () => {
      window.removeEventListener(
        "product-factory:provider-credential-changed",
        refreshFromCredentialChange,
      );
      window.removeEventListener(
        "product-factory:codex-runtime-confirmed",
        refreshFromConfirmation,
      );
    };
  }, []);

  async function checkCompatibility() {
    setPending(true);
    setError("");
    try {
      const response = await fetch(checkEndpoint, { method: "POST" });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error?.user_message ?? "Codex 兼容性检测失败");
      }
      setStatus((await response.json()) as CodexRuntimeCapabilityStatus);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Codex 兼容性检测失败");
    } finally {
      setPending(false);
    }
  }

  const checks = [
    ["App Server", status.checks.app_server],
    ["Responses", status.checks.responses_api],
    ["流式输出", status.checks.streaming],
    ["结构化输出", status.checks.structured_output],
    ["工具调用", status.checks.tool_calling],
    ["Key 隔离", status.checks.secret_isolation],
  ] as const;

  return (
    <section aria-labelledby="codex-runtime-title" className="api-key-settings">
      <header>
        <div>
          <p className="eyebrow">CODEX COMPATIBILITY / API 确认</p>
          <h2 id="codex-runtime-title">API 可用性确认</h2>
        </div>
        <span className={codexCompatibilityClass(status)}>
          {codexCompatibilityLabel(status)}
        </span>
      </header>
      <p className="api-key-explanation">
        “已保存”不等于“已可用”。确认 API 会使用当前账户保存的模型 API 启动隔离的 Codex App Server，检测真实流式输出、结构化输出和工具调用。检测不会把 Key 写入数据库、页面回包或 Codex 配置文件。
      </p>
      <div className="codex-capability-grid" aria-label="Codex 能力检测结果">
        {checks.map(([label, passed]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{passed ? "通过" : "未验证"}</strong>
          </div>
        ))}
      </div>
      <div aria-live="polite" className="api-key-state">
        <span>{status.user_message ?? "尚未执行检测。"}</span>
        <button
          className="secondary-button"
          disabled={!status.configured || pending}
          onClick={checkCompatibility}
          type="button"
        >
          {pending
            ? "确认中…"
            : status.compatibility === "compatible"
              ? "重新确认 API"
              : "确认 API"}
        </button>
      </div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </section>
  );
}
