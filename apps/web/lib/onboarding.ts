import type { SessionStatus } from "@/lib/contracts";

export const onboardingSteps = [
  { title: "从真实想法开始", body: "输入产品想法后，系统先创建真实项目并形成 Project Brief，不伪造 Agent 回复。" },
  { title: "先连接你的 AI", body: "前往设置页添加专属于你的 API Key 和模型接口。Agent 会使用你的 API 额度执行任务，Key 原文不会进入项目或产物。", settingsLink: true },
  { title: "沿 12 阶段推进", body: "项目从对齐走到数据与反馈；G0–G6 是必须由你确认的业务决策。" },
  { title: "群聊管指令，画布管事实", body: "在左侧向团队下指令，在右侧查看随项目阶段累计的 Artifact DAG。" },
  { title: "高风险动作始终留给你", body: "Gate 决定和一次性 Permission 独立存在，Agent 不会自动批准或伪造成功态。" },
] as const;

export function onboardingAllowed(
  session: Pick<SessionStatus, "auth_enforced" | "authenticated">,
) {
  return !session.auth_enforced || session.authenticated;
}

export function shouldAutoOpenOnboarding(
  session: Pick<SessionStatus, "auth_enforced" | "authenticated">,
  pathname: string,
  seen: boolean,
) {
  return pathname === "/" && !seen && onboardingAllowed(session);
}
