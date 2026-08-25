import type { SessionStatus } from "@/lib/contracts";

export const onboardingSteps = [
  { title: "从真实想法开始", body: "输入产品想法后，系统先创建真实项目并形成 Project Brief，不伪造 Agent 回复。" },
  { title: "先建立你的本地账户", body: "引导结束后创建企业本地账户。你的项目、产物和 API 配置都会归属于这个账户。" },
  { title: "沿 12 阶段推进", body: "项目从对齐走到数据与反馈；G0–G6 是必须由你确认的业务决策。" },
  { title: "群聊管指令，画布管事实", body: "在左侧向团队下指令，在右侧查看随项目阶段累计的 Artifact DAG。" },
  { title: "高风险动作始终留给你", body: "Gate 决定和一次性 Permission 独立存在，Agent 不会自动批准或伪造成功态。" },
] as const;

export function onboardingAllowed(
  session: Pick<SessionStatus, "auth_enforced" | "authenticated">,
) {
  return !session.authenticated;
}

export function onboardingStorageKey() {
  return "product-factory:onboarding:v3:pre-auth";
}

export function shouldAutoOpenOnboarding(
  session: Pick<SessionStatus, "auth_enforced" | "authenticated">,
  pathname: string,
  seen: boolean,
) {
  return pathname === "/" && !seen && onboardingAllowed(session);
}
