export type HeaderPopoverId = "notifications" | "help" | "identity";

export function nextHeaderPopover(
  current: HeaderPopoverId | null,
  requested: HeaderPopoverId,
) {
  return current === requested ? null : requested;
}
