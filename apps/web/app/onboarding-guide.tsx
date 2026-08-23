"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { SessionStatus } from "@/lib/contracts";
import { onboardingAllowed, onboardingSteps, shouldAutoOpenOnboarding } from "@/lib/onboarding";

const storageKey = "product-factory:onboarding:v1";
export function OnboardingGuide() {
  const pathname = usePathname();
  const panel = useRef<HTMLElement>(null);
  const [allowed, setAllowed] = useState(false);
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch("/api/control/api/v1/me", { cache: "no-store" });
        if (!response.ok) throw new Error("会话状态读取失败");
        const session = (await response.json()) as SessionStatus;
        if (!active) return;
        const canShow = onboardingAllowed(session);
        setAllowed(canShow);
        if (!canShow) {
          setOpen(false);
          return;
        }
        if (shouldAutoOpenOnboarding(
          session,
          pathname,
          window.localStorage.getItem(storageKey) === "seen",
        )) {
          window.localStorage.setItem(storageKey, "seen");
          setStep(0);
          setOpen(true);
        }
      } catch {
        if (active) {
          setAllowed(false);
          setOpen(false);
        }
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
    const show = () => {
      if (!allowed || pathname !== "/") return;
      setStep(0);
      setOpen(true);
      window.setTimeout(() => panel.current?.focus(), 0);
    };
    window.addEventListener("product-factory:open-onboarding", show);
    return () => window.removeEventListener("product-factory:open-onboarding", show);
  }, [allowed, pathname]);

  function finish() {
    window.localStorage.setItem(storageKey, "seen");
    setOpen(false);
  }

  if (!allowed || !open || pathname !== "/") return null;
  const current = onboardingSteps[step];

  return (
    <>
      <div aria-hidden="true" className="onboarding-backdrop" />
      <aside
        aria-describedby="onboarding-description"
        aria-labelledby="onboarding-title"
        aria-modal="true"
        className="onboarding-panel"
        ref={panel}
        role="dialog"
        tabIndex={-1}
      >
        <header>
          <span>FIRST RUN / {step + 1} OF {onboardingSteps.length}</span>
          <button aria-label="跳过首次引导" onClick={finish} type="button">跳过</button>
        </header>
        <div aria-live="polite" className="onboarding-content">
          <strong aria-hidden="true" className="onboarding-number">0{step + 1}</strong>
          <div>
            <h2 id="onboarding-title">{current.title}</h2>
            <p id="onboarding-description">{current.body}</p>
            {"settingsLink" in current ? <a className="onboarding-settings-link" href="/settings">去设置 API Key</a> : null}
          </div>
        </div>
        <ol aria-label="引导进度" className="onboarding-progress">
          {onboardingSteps.map((item, index) => <li aria-current={index === step ? "step" : undefined} key={item.title}><span className="sr-only">第 {index + 1} 步</span></li>)}
        </ol>
        <footer>
          <button disabled={step === 0} onClick={() => setStep((value) => value - 1)} type="button">上一步</button>
          <button className="primary-button" onClick={() => step === onboardingSteps.length - 1 ? finish() : setStep((value) => value + 1)} type="button">
            {step === onboardingSteps.length - 1 ? "开始使用" : "下一步"}
          </button>
        </footer>
      </aside>
    </>
  );
}
