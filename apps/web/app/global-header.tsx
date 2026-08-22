"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { GateRequest, PermissionRequest, Project } from "@/lib/contracts";
import { nextHeaderPopover, type HeaderPopoverId } from "@/lib/header";
import type { AttentionItem } from "@/lib/home";
import { localUser } from "@/lib/identity";

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
  const [activePopover, setActivePopover] = useState<HeaderPopoverId | null>(null);
  const headerTools = useRef<HTMLDivElement>(null);
  const popoverTriggers = useRef<Partial<Record<HeaderPopoverId, HTMLElement>>>({});

  useEffect(() => {
    let active = true;
    const refresh = () => {
      setAttentionState("loading");
      loadAttention().then((items) => {
        if (!active) return;
        setAttention(items);
        setAttentionState("ready");
      }).catch(() => {
        if (active) setAttentionState("error");
      });
    };
    refresh();
    window.addEventListener("focus", refresh);
    return () => {
      active = false;
      window.removeEventListener("focus", refresh);
    };
  }, [pathname]);

  useEffect(() => {
    function onShortcut(event: KeyboardEvent) {
      if (event.key !== "?" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) return;
      event.preventDefault();
      popoverTriggers.current.help?.focus();
      setActivePopover("help");
    }
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

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

  function openOnboarding() {
    setActivePopover(null);
    window.dispatchEvent(new CustomEvent("product-factory:open-onboarding"));
  }

  function focusProjectList() {
    if (pathname !== "/") return;
    window.setTimeout(() => document.getElementById("projects")?.focus({ preventScroll: true }), 0);
  }

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
            <Link aria-current={pathname === "/" ? "page" : undefined} href="/#projects" onClick={focusProjectList}>项目列表</Link>
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
            <details className="header-popover" open={activePopover === "help"}>
              <summary
                aria-keyshortcuts="?"
                onClick={(event) => {
                  event.preventDefault();
                  togglePopover("help");
                }}
                ref={(node) => { if (node) popoverTriggers.current.help = node; }}
              >帮助</summary>
              <div className="header-popover-panel help-panel">
                <strong>使用帮助</strong>
                <button onClick={openOnboarding} type="button">重新打开首次引导</button>
                <p><kbd>/</kbd> 聚焦项目搜索　<kbd>?</kbd> 打开帮助</p>
                <p>关键 Gate 必须由你决定；Agent 不会自动越过。</p>
              </div>
            </details>
            <details className="header-popover identity-popover" open={activePopover === "identity"}>
              <summary
                aria-label={`${localUser.displayName}，${localUser.role}`}
                onClick={(event) => {
                  event.preventDefault();
                  togglePopover("identity");
                }}
                ref={(node) => { if (node) popoverTriggers.current.identity = node; }}
              >{localUser.displayName}</summary>
              <div className="header-popover-panel identity-panel">
                <span className="identity-avatar" aria-hidden="true">我</span>
                <div>
                  <strong>{localUser.role}</strong>
                  <small>{localUser.id}</small>
                </div>
                <dl>
                  <div><dt>运行模式</dt><dd>{localUser.mode}</dd></div>
                  <div><dt>身份认证</dt><dd>{localUser.authStatus}</dd></div>
                </dl>
                <p>当前身份仅用于单机控制面署名，不代表已建立登录 Session。</p>
              </div>
            </details>
          </div>
        </div>
      </header>
    </>
  );
}
