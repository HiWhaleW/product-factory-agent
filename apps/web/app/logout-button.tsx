"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function logout() {
    setPending(true);
    try {
      await fetch("/api/control/api/v1/auth/session", { method: "DELETE" });
      window.dispatchEvent(new CustomEvent("product-factory:session-changed"));
      router.push("/");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return <button disabled={pending} onClick={logout} type="button">{pending ? "正在退出…" : "退出登录"}</button>;
}
