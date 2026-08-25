"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import type { ApiError, SessionStatus } from "@/lib/contracts";

type AccessMode = "register" | "login";

export function LoginForm() {
  const router = useRouter();
  const [mode, setMode] = useState<AccessMode>("register");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  function selectMode(nextMode: AccessMode) {
    setMode(nextMode);
    setError("");
    setPassword("");
    setConfirmation("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username || !password || pending) return;
    if (mode === "register" && password !== confirmation) {
      setError("两次输入的密码不一致。");
      return;
    }
    setPending(true);
    setError("");
    try {
      const endpoint = mode === "register"
        ? "/api/control/api/v1/auth/register"
        : "/api/control/api/v1/auth/session";
      const payload = mode === "register"
        ? { username, display_name: displayName, password }
        : { username, password };
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await response.json()) as SessionStatus & ApiError;
      if (!response.ok || !body.authenticated) {
        throw new Error(body.error?.user_message ?? "账户操作失败，请检查输入。");
      }
      setPassword("");
      setConfirmation("");
      window.dispatchEvent(new CustomEvent("product-factory:session-changed"));
      router.replace("/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof TypeError
        ? "网络连接失败，请稍后重试。"
        : reason instanceof Error ? reason.message : "账户操作失败，请稍后重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="login-form account-form" onSubmit={submit}>
      <div aria-label="账户操作" className="account-mode-tabs" role="tablist">
        <button aria-selected={mode === "register"} onClick={() => selectMode("register")} role="tab" type="button">创建账户</button>
        <button aria-selected={mode === "login"} onClick={() => selectMode("login")} role="tab" type="button">已有账户登录</button>
      </div>
      <header>
        <strong>{mode === "register" ? "创建企业本地账户" : "登录企业本地账户"}</strong>
        <span>{mode === "register" ? "账户和项目只保存在企业自己的部署环境中。" : "登录后继续查看这个账户创建的项目。"}</span>
      </header>
      <label htmlFor="account-username"><strong>登录账号</strong><span>3–64 位英文字母、数字、点、下划线或连字符</span></label>
      <input autoComplete="username" id="account-username" name="username" onChange={(event) => setUsername(event.target.value)} pattern="[A-Za-z0-9._-]{3,64}" required value={username} />
      {mode === "register" ? (
        <>
          <label htmlFor="account-display-name"><strong>显示名称</strong></label>
          <input autoComplete="name" id="account-display-name" name="display-name" onChange={(event) => setDisplayName(event.target.value)} required value={displayName} />
        </>
      ) : null}
      <label htmlFor="account-password"><strong>密码</strong><span>至少 8 位</span></label>
      <input autoComplete={mode === "register" ? "new-password" : "current-password"} id="account-password" minLength={8} name="password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
      {mode === "register" ? (
        <>
          <label htmlFor="account-password-confirm"><strong>确认密码</strong></label>
          <input autoComplete="new-password" id="account-password-confirm" minLength={8} name="password-confirm" onChange={(event) => setConfirmation(event.target.value)} required type="password" value={confirmation} />
        </>
      ) : null}
      <button className="primary-button account-submit" disabled={pending} type="submit">
        {pending ? "正在处理…" : mode === "register" ? "创建并进入" : "登录"}
      </button>
      {error ? <p aria-live="polite" className="form-error">{error}</p> : null}
    </form>
  );
}
