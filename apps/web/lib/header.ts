import type { SessionStatus } from "@/lib/contracts";

export type HeaderPopoverId = "notifications" | "identity";

export function identityPresentation(session: SessionStatus | null) {
  const authenticated = Boolean(session?.authenticated);
  return {
    displayName: authenticated ? session?.display_name ?? "我" : "访客",
    accountLabel: session?.role === "admin"
      ? "管理员账号"
      : session?.role === "user" ? "企业账号" : "访客",
    loginLabel: authenticated ? "已登录" : session?.auth_enforced ? "需要登录" : "未启用登录",
  };
}

export function nextHeaderPopover(
  current: HeaderPopoverId | null,
  requested: HeaderPopoverId,
) {
  return current === requested ? null : requested;
}
