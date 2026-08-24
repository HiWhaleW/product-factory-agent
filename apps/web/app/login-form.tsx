"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import type { ApiError, SessionStatus } from "@/lib/contracts";

export function LoginForm() {
  const router = useRouter();
  const [inviteCode, setInviteCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!inviteCode || pending) return;
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/control/api/v1/auth/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ invite_code: inviteCode }),
      });
      const body = (await response.json()) as SessionStatus & ApiError;
      if (!response.ok || !body.authenticated) {
        throw new Error(body.error?.user_message ?? "登录失败，请检查邀请码。");
      }
      setInviteCode("");
      window.dispatchEvent(new CustomEvent("product-factory:session-changed"));
      router.replace("/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof TypeError
        ? "网络连接失败，请稍后重试。"
        : reason instanceof Error ? reason.message : "登录失败，请稍后重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="login-form" onSubmit={submit}>
      <label htmlFor="invite-code">
        <strong>进入造物工场</strong>
        <span>请输入管理员提供的邀请码</span>
      </label>
      <input
        autoComplete="one-time-code"
        id="invite-code"
        name="invite-code"
        onChange={(event) => setInviteCode(event.target.value)}
        required
        type="password"
        value={inviteCode}
      />
      <button className="primary-button" disabled={pending} type="submit">
        {pending ? "正在验证…" : "登录"}
      </button>
      {error ? <p aria-live="polite" className="form-error">{error}</p> : null}
    </form>
  );
}
