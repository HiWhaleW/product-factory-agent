"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LoginForm } from "@/app/login-form";
import type { SessionStatus } from "@/lib/contracts";
import { onboardingSteps, onboardingStorageKey } from "@/lib/onboarding";

type OnboardingMode = "closed" | "guide" | "auth";

export function OnboardingGuide() {
  const pathname = usePathname();
  const panel = useRef<HTMLElement>(null);
  const [mode, setMode] = useState<OnboardingMode>("closed");
  const [step, setStep] = useState(0);
  const [authEnforced, setAuthEnforced] = useState(false);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch("/api/control/api/v1/me", { cache: "no-store" });
        if (!response.ok) throw new Error("会话状态读取失败");
        const session = (await response.json()) as SessionStatus;
        if (!active) return;
        setAuthEnforced(session.auth_enforced);
        if (pathname !== "/" || session.authenticated) {
          setMode("closed");
          return;
        }
        const seen = window.localStorage.getItem(onboardingStorageKey()) === "seen";
        setMode(seen && session.auth_enforced ? "auth" : "guide");
      } catch {
        if (active) setMode("closed");
      }
    };
    void refresh();
    window.addEventListener("product-factory:session-changed", refresh);
    return () => {
      active = false;
      window.removeEventListener("product-factory:session-changed", refresh);
    };
  }, [pathname]);

  useEffect(() => {
    if (mode !== "closed") window.setTimeout(() => panel.current?.focus(), 0);
  }, [mode]);

  function finishGuide() {
    window.localStorage.setItem(onboardingStorageKey(), "seen");
    setMode(authEnforced ? "auth" : "closed");
  }

  if (mode === "closed" || pathname !== "/") return null;
  if (mode === "auth") {
    return (
      <>
        <div aria-hidden="true" className="onboarding-backdrop" />
        <aside aria-label="创建账户或登录" aria-modal="true" className="onboarding-panel account-access-panel" ref={panel} role="dialog" tabIndex={-1}>
          <LoginForm />
        </aside>
      </>
    );
  }

  const current = onboardingSteps[step];
  return (
    <>
      <div aria-hidden="true" className="onboarding-backdrop" />
      <aside aria-describedby="onboarding-description" aria-labelledby="onboarding-title" aria-modal="true" className="onboarding-panel" ref={panel} role="dialog" tabIndex={-1}>
        <header>
          <span>FIRST RUN / {step + 1} OF {onboardingSteps.length}</span>
          <button aria-label="跳过首次引导" onClick={finishGuide} type="button">跳过</button>
        </header>
        <div aria-live="polite" className="onboarding-content">
          <strong aria-hidden="true" className="onboarding-number">0{step + 1}</strong>
          <div>
            <h2 id="onboarding-title">{current.title}</h2>
            <p id="onboarding-description">{current.body}</p>
          </div>
        </div>
        <ol aria-label="引导进度" className="onboarding-progress">
          {onboardingSteps.map((item, index) => <li aria-current={index === step ? "step" : undefined} key={item.title}><span className="sr-only">第 {index + 1} 步</span></li>)}
        </ol>
        <footer>
          <button disabled={step === 0} onClick={() => setStep((value) => value - 1)} type="button">上一步</button>
          <button className="primary-button" onClick={() => step === onboardingSteps.length - 1 ? finishGuide() : setStep((value) => value + 1)} type="button">
            {step === onboardingSteps.length - 1 ? "创建账户" : "下一步"}
          </button>
        </footer>
      </aside>
    </>
  );
}
