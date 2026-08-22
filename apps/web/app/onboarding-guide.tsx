"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const storageKey = "product-factory:onboarding:v1";
const steps = [
  { title: "从真实想法开始", body: "输入产品想法后，系统先创建真实项目并形成 Project Brief，不伪造 Agent 回复。" },
  { title: "沿 12 阶段推进", body: "项目从对齐走到数据与反馈；G0–G6 是必须由你确认的业务决策。" },
  { title: "群聊管指令，画布管事实", body: "在左侧向团队下指令，在右侧查看随项目阶段累计的 Artifact DAG。" },
  { title: "高风险动作始终留给你", body: "Gate 决定和一次性 Permission 独立存在，Agent 不会自动批准或伪造成功态。" },
] as const;

export function OnboardingGuide() {
  const pathname = usePathname();
  const panel = useRef<HTMLElement>(null);
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    const show = () => {
      setStep(0);
      setOpen(true);
      window.setTimeout(() => panel.current?.focus(), 0);
    };
    window.addEventListener("product-factory:open-onboarding", show);
    if (pathname === "/" && window.localStorage.getItem(storageKey) !== "seen") show();
    return () => window.removeEventListener("product-factory:open-onboarding", show);
  }, [pathname]);

  function finish() {
    window.localStorage.setItem(storageKey, "seen");
    setOpen(false);
  }

  if (!open || pathname !== "/") return null;
  const current = steps[step];

  return (
    <aside
      aria-describedby="onboarding-description"
      aria-labelledby="onboarding-title"
      aria-modal="false"
      className="onboarding-panel"
      ref={panel}
      role="dialog"
      tabIndex={-1}
    >
      <header>
        <span>FIRST RUN / {step + 1} OF {steps.length}</span>
        <button aria-label="跳过首次引导" onClick={finish} type="button">跳过</button>
      </header>
      <div aria-live="polite" className="onboarding-content">
        <strong aria-hidden="true" className="onboarding-number">0{step + 1}</strong>
        <div>
          <h2 id="onboarding-title">{current.title}</h2>
          <p id="onboarding-description">{current.body}</p>
        </div>
      </div>
      <ol aria-label="引导进度" className="onboarding-progress">
        {steps.map((item, index) => <li aria-current={index === step ? "step" : undefined} key={item.title}><span className="sr-only">第 {index + 1} 步</span></li>)}
      </ol>
      <footer>
        <button disabled={step === 0} onClick={() => setStep((value) => value - 1)} type="button">上一步</button>
        <button className="primary-button" onClick={() => step === steps.length - 1 ? finish() : setStep((value) => value + 1)} type="button">
          {step === steps.length - 1 ? "开始使用" : "下一步"}
        </button>
      </footer>
    </aside>
  );
}
