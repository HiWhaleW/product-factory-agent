"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LogoutButton } from "@/app/logout-button";

import type { GateRequest, PermissionRequest, Project, ProviderCredentialStatus, ResearchCredentialStatus, SessionStatus } from "@/lib/contracts";
import { identityPresentation, nextHeaderPopover, type HeaderPopoverId } from "@/lib/header";
import type { AttentionItem } from "@/lib/home";

type GlobalAttentionItem = AttentionItem & { projectId: string; projectName: string };

async function loadAttention() {
  const projectResponse = await fetch("/api/control/api/v1/projects", { cache: "no-store" });
  if (!projectResponse.ok) throw new Error("项目列表读取失败");
  const projects = (await projectResponse.json()) as Project[];

  const items = await Promise.all(projects.map(async (project) => {
    const [gateResponse, permissionResponse] = await Promise.all([
      fetch(`/api/control/api/v1/projects/${project.id}/gates`, { cache: "no-store" }),
      fetch(`/api/control/api/v1/projects/${project.id}/permissions`, { cache: "no-store" }),
    ]);
    if (!gateResponse.ok || !permissionResponse.ok) throw new Error("待处理状态读取失败");
    const gates = (await gateResponse.json()) as GateRequest[];
    const permissions = (await permissionResponse.json()) as PermissionRequest[];
    return [
      ...gates.filter((gate) => gate.status === "open").map((gate) => ({
        id: gate.id,
        kind: "gate" as const,
        label: `${gate.gate_type} 产品决策`,
        createdAt: gate.opened_at,
        projectId: project.id,
        projectName: project.name,
      })),
      ...permissions.filter((permission) => permission.status === "open").map((permission) => ({
        id: permission.id,
        kind: "permission" as const,
        label: `${permission.tool_name} 工具权限`,
        createdAt: permission.created_at,
        projectId: project.id,
        projectName: project.name,
      })),
    ];
  }));

  return items.flat().sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function GlobalHeader({ productName }: { productName: string }) {
  const pathname = usePathname();
  const [attention, setAttention] = useState<GlobalAttentionItem[]>([]);
  const [attentionState, setAttentionState] = useState<"loading" | "ready" | "error">("loading");
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [providerCredential, setProviderCredential] = useState<ProviderCredentialStatus | null>(null);
  const [researchCredential, setResearchCredential] = useState<ResearchCredentialStatus | null>(null);
  const [activePopover, setActivePopover] = useState<HeaderPopoverId | null>(null);
  const headerTools = useRef<HTMLDivElement>(null);
  const popoverTriggers = useRef<Partial<Record<HeaderPopoverId, HTMLElement>>>({});

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      setAttentionState("loading");
      try {
        const sessionResponse = await fetch("/api/control/api/v1/me", { cache: "no-store" });
        if (!sessionResponse.ok) throw new Error("会话状态读取失败");
        const currentSession = (await sessionResponse.json()) as SessionStatus;
        if (!active) return;
        setSession(currentSession);
        if (currentSession.auth_enforced && !currentSession.authenticated) {
          setProviderCredential(null);
          setResearchCredential(null);
          setAttention([]);
          setAttentionState("ready");
          return;
        }
        const [items, providerResponse, researchResponse] = await Promise.all([
          loadAttention(),
          fetch("/api/control/api/v1/me/provider-credentials/model-api", { cache: "no-store" }),
          fetch("/api/control/api/v1/me/provider-credentials/web-search", { cache: "no-store" }),
        ]);
        if (!providerResponse.ok || !researchResponse.ok) throw new Error("API 配置读取失败");
        const provider = (await providerResponse.json()) as ProviderCredentialStatus;
        const research = (await researchResponse.json()) as ResearchCredentialStatus;
        if (!active) return;
        setProviderCredential(provider);
        setResearchCredential(research);
        setAttention(items);
        setAttentionState("ready");
      } catch {
        if (active) setAttentionState("error");
      }
    };
    void refresh();
    const refreshFromEvent = () => void refresh();
    window.addEventListener("focus", refreshFromEvent);
    window.addEventListener("product-factory:session-changed", refreshFromEvent);
    window.addEventListener("product-factory:provider-credential-changed", refreshFromEvent);
    return () => {
      active = false;
      window.removeEventListener("focus", refreshFromEvent);
      window.removeEventListener("product-factory:session-changed", refreshFromEvent);
      window.removeEventListener("product-factory:provider-credential-changed", refreshFromEvent);
    };
  }, [pathname]);

  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      if (event.target instanceof Node && !headerTools.current?.contains(event.target)) {
        setActivePopover(null);
      }
    }

    function closeWithEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || !activePopover) return;
      event.preventDefault();
      const trigger = popoverTriggers.current[activePopover];
      trigger?.focus();
      setActivePopover(null);
    }

    document.addEventListener("pointerdown", closeOutside);
    window.addEventListener("keydown", closeWithEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      window.removeEventListener("keydown", closeWithEscape);
    };
  }, [activePopover]);

  function togglePopover(popover: HeaderPopoverId) {
    setActivePopover((current) => nextHeaderPopover(current, popover));
  }

  const { accountLabel, displayName, loginLabel } = identityPresentation(session);

  return (
    <>
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <header className="global-header">
        <Link aria-current={pathname === "/" ? "page" : undefined} className="brand" href="/">
          <Image alt="" aria-hidden="true" height={40} priority src="/workshop-mark.png" width={40} />
          <span>{productName}</span>
        </Link>
        <div className="header-navigation">
          <nav aria-label="主导航">
            <Link aria-current={pathname === "/" ? "page" : undefined} href="/">首页</Link>
            <Link aria-current={pathname.startsWith("/projects") ? "page" : undefined} href="/projects">项目列表</Link>
            <Link aria-current={pathname === "/settings" ? "page" : undefined} href="/settings">设置</Link>
          </nav>
          <div aria-label="全局工具" className="header-tools" ref={headerTools}>
            <details className="header-popover notification-popover" open={activePopover === "notifications"}>
              <summary
                aria-label={attentionState === "ready" ? `通知，${attention.length} 项待处理` : "通知状态"}
                onClick={(event) => {
                  event.preventDefault();
                  togglePopover("notifications");
                }}
                ref={(node) => { if (node) popoverTriggers.current.notifications = node; }}
              >
                通知
                <span aria-hidden="true" className="header-count">
                  {attentionState === "loading" ? "…" : attentionState === "error" ? "!" : attention.length}
                </span>
              </summary>
              <div className="header-popover-panel" role="status">
                <strong>等待我处理</strong>
                {attentionState === "error" ? <p>控制面状态读取失败，请刷新后重试。</p> : null}
                {attentionState === "ready" && !attention.length ? <p>当前没有真实开放的 Gate 或 Permission。</p> : null}
                {attention.map((item) => (
                  <Link
                    href={`/projects/${item.projectId}`}
                    key={`${item.kind}-${item.id}`}
                    onClick={() => setActivePopover(null)}
                  >
                    <span>{item.kind === "gate" ? "GATE" : "PERMISSION"}</span>
                    <strong>{item.label}</strong>
                    <small>{item.projectName}</small>
                  </Link>
                ))}
              </div>
            </details>
            <details className="header-popover identity-popover" open={activePopover === "identity"}>
              <summary
                aria-label={`${displayName}，${accountLabel}，${loginLabel}`}
                onClick={(event) => {
                  event.preventDefault();
                  togglePopover("identity");
                }}
                ref={(node) => { if (node) popoverTriggers.current.identity = node; }}
              >个人信息</summary>
              <div className="header-popover-panel identity-panel">
                <span className="identity-avatar" aria-hidden="true">我</span>
                <div>
                  <strong>{displayName}</strong>
                  <small>{accountLabel}</small>
                </div>
                <dl>
                  <div><dt>登录账号</dt><dd>{session?.username ?? "—"}</dd></div>
                  <div><dt>账户身份</dt><dd>{accountLabel}</dd></div>
                  <div><dt>登录状态</dt><dd>{loginLabel}</dd></div>
                  <div><dt>API 厂商</dt><dd>{providerCredential?.configured ? providerCredential.provider_name : "未配置"}</dd></div>
                  <div><dt>模型</dt><dd>{providerCredential?.configured ? providerCredential.model_name : "未配置"}</dd></div>
                  <div><dt>网络搜索厂商</dt><dd>{researchCredential?.configured ? researchCredential.provider_name : "未配置"}</dd></div>
                </dl>
                {session?.authenticated ? <LogoutButton /> : null}
              </div>
            </details>
          </div>
        </div>
      </header>
    </>
  );
}
