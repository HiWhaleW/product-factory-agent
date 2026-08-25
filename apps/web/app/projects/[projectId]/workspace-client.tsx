"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import type {
  ApiError,
  ArtifactGraph,
  ArtifactNode,
  GateRequest,
  Message,
  PermissionRequest,
  Project,
  ProjectEvent,
} from "@/lib/contracts";
import { eventStreamSync, parseAgUiProjectEvent } from "@/lib/ag-ui-events";
import { projectStageIndex, projectStageLabel, projectStages } from "@/lib/stages";
import {
  agentIntroduction,
  artifactPanelTitle,
  composeReferencedMessage,
  eventPresentation,
  friendlyProcessStep,
  groupProcessEventsForConversation,
  isChatMilestoneEvent,
  parseReferencedMessage,
  plainLanguageAgentMessage,
  projectAgentProfile,
  projectAgentProfiles,
  processActorProfile,
  stageStartEventId,
} from "@/lib/workspace";

const ArtifactDag = dynamic(
  () => import("@/app/projects/[projectId]/artifact-dag").then((module) => module.ArtifactDag),
  { ssr: false, loading: () => <div className="dag-loading">正在载入产物画布…</div> },
);

const timeFormatter = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" });
function formatTime(value: string) {
  return timeFormatter.format(new Date(value));
}

type TimelineItem =
  | { type: "message"; id: string; createdAt: string; message: Message }
  | { type: "event"; id: string; createdAt: string; event: ProjectEvent }
  | { type: "gate"; id: string; createdAt: string; gate: GateRequest }
  | { type: "permission"; id: string; createdAt: string; permission: PermissionRequest }
  | { type: "process"; id: string; createdAt: string; events: ProjectEvent[]; label: string; state: string };

function messageIdentity(message: Message) {
  if (message.actor_type === "user") {
    return { avatar: "我", label: "你", tone: "user" };
  }
  const participant = projectAgentProfile(message.actor_id);
  return participant
    ? { avatar: participant.avatar, label: participant.label, tone: participant.name.toLowerCase().replace(" ", "-") }
    : { avatar: "A", label: message.actor_id || "Agent", tone: "agent" };
}

function ConversationMessage({ message }: { message: Message }) {
  const identity = messageIdentity(message);
  const content = parseReferencedMessage(message.content);
  const visibleBody = message.actor_type === "user"
    ? content.body
    : plainLanguageAgentMessage(content.body);
  return (
    <article className={`conversation-message actor-${identity.tone}`}>
      <span aria-hidden="true" className="conversation-avatar">
        {identity.tone === "user" ? <Image alt="" height={42} src="/icon-user-message.png" width={42} /> : identity.avatar}
      </span>
      <div className="conversation-message-body">
        <header><strong>{identity.label}</strong><time>{formatTime(message.created_at)}</time></header>
        <div className="conversation-bubble">
          {content.reference ? (
            <span className="message-artifact-reference">引用产物 · {content.reference.title} · v{content.reference.version}</span>
          ) : null}
          {visibleBody ? <p>{visibleBody}</p> : null}
        </div>
      </div>
    </article>
  );
}

function ConversationEvent({ elementId, event }: { elementId: string; event: ProjectEvent }) {
  const presentation = eventPresentation(event);
  if (presentation.tone === "agent") {
    const introduction = agentIntroduction(event);
    if (introduction) {
      const isLead = introduction.profile.id === "factory-lead";
      return (
        <section className="agent-join-sequence" id={elementId}>
          <article className={`conversation-agent-arrival arrival-${introduction.profile.tone}`}>
            <div aria-hidden="true" className="agent-arrival-visual">
              <span className="arrival-avatar arrival-host">主</span>
              <span className="arrival-route"><i>✦</i><i>·</i><i>·</i><i>➜</i></span>
              <span className="arrival-avatar arrival-guest">{introduction.profile.avatar}</span>
            </div>
            <p>{isLead
              ? <><strong>主 Agent</strong> 创建了项目群聊，正在组建团队</>
              : <><strong>主 Agent</strong> 邀请 <strong>{introduction.profile.label}</strong> 加入群聊</>}</p>
            <time>{formatTime(event.created_at)}</time>
          </article>
          <article className={`conversation-message actor-${introduction.profile.name.toLowerCase().replace(" ", "-")}`}>
            <span aria-hidden="true" className="conversation-avatar">{introduction.profile.avatar}</span>
            <div className="conversation-message-body">
              <header><strong>{introduction.profile.label}</strong><time>{formatTime(event.created_at)}</time></header>
              <div className="conversation-bubble"><p>{introduction.text}</p></div>
            </div>
          </article>
        </section>
      );
    }
    return (
      <article className="conversation-narration" id={elementId}>
        <span aria-hidden="true" />
        <p>{presentation.summary}</p>
        <span aria-hidden="true" />
      </article>
    );
  }
  return (
    <article className="conversation-narration" id={elementId}>
      <span aria-hidden="true" />
      <p>{presentation.summary}</p>
      <span aria-hidden="true" />
    </article>
  );
}

function ProcessLedger({ events, label, state }: { events: ProjectEvent[]; label: string; state: string }) {
  const actor = processActorProfile(events);
  const processTitle = actor ? `${actor.label} 的处理过程` : "系统处理过程";
  return (
    <details className="conversation-process-ledger" data-stage={state}>
      <summary>
        <span>{label}</span>
        <strong>{processTitle}</strong>
        <small>{events.length} 项进展</small>
      </summary>
      <ol>
        {events.map((event) => {
          const step = friendlyProcessStep(event);
          return (
            <li key={event.id}>
              <time>{formatTime(event.created_at)}</time>
              <div>
                <strong>{step.label}</strong>
                <p>{step.summary}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </details>
  );
}

function GateConversationCard({
  comment,
  confirmingKill,
  disabled,
  gate,
  onComment,
  onDecision,
  onKillCancel,
  onKillRequest,
}: {
  comment: string;
  confirmingKill: boolean;
  disabled: boolean;
  gate: GateRequest;
  onComment: (value: string) => void;
  onDecision: (decision: "approve" | "changes" | "pause" | "kill") => void;
  onKillCancel: () => void;
  onKillRequest: () => void;
}) {
  const isOpen = gate.status === "open";
  return (
    <article className={`gate-card conversation-control${isOpen ? "" : " gate-card-history"}`}>
      <div className="control-card-heading">
        <Image alt="" className="control-card-icon" height={42} src="/icon-gate-card.png" width={42} />
        <div>
          <span className="control-kind">{isOpen ? "需要你选择" : "历史记录"} · 阶段确认</span>
          <strong>是否进入 {gate.target_state ? projectStageLabel(gate.target_state) : "既定下一阶段"}？</strong>
        </div>
      </div>
      <p>{isOpen
        ? "只有你可以决定是否进入下一阶段，普通群聊不会代替这个决定。"
        : "这项阶段决定已经记录，下方保留当时的依据和已知问题。"}</p>
      {gate.reason ? (
        <div className="gate-basis">
          <strong>审批依据</strong>
          <p>{gate.reason}</p>
          {gate.impacted_artifact_refs.length ? (
            <small>关联 {gate.impacted_artifact_refs.length} 个真实产物版本</small>
          ) : null}
        </div>
      ) : null}
      {gate.known_issues.length ? (
        <div className="gate-basis known-issues">
          <strong>已知问题</strong>
          <ul>
            {gate.known_issues.map((issue) => (
              <li key={`${issue.severity}:${issue.issue}`}>
                <b>{issue.severity}</b> · {issue.issue} · {issue.status === "open" ? "待验证" : issue.status}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {isOpen ? <label htmlFor={`gate-comment-${gate.id}`}>原因（批准可选，其他选项必填）</label> : null}
      {isOpen ? (
        <textarea
          id={`gate-comment-${gate.id}`}
          onChange={(event) => onComment(event.target.value)}
          rows={2}
          value={comment}
        />
      ) : null}
      {isOpen && confirmingKill ? (
        <div className="inline-confirm" role="alert">
          <p>确认终止这个项目？该决定无法由普通消息撤销。</p>
          <div className="button-row">
            <button className="danger-button" disabled={disabled} onClick={() => onDecision("kill")} type="button">确认终止</button>
            <button disabled={disabled} onClick={onKillCancel} type="button">取消</button>
          </div>
        </div>
      ) : isOpen ? (
        <div className="button-row">
          <button className="primary-button" disabled={disabled} onClick={() => onDecision("approve")} type="button">批准并推进</button>
          <button disabled={disabled} onClick={() => onDecision("changes")} type="button">退回修改</button>
          <button disabled={disabled} onClick={() => onDecision("pause")} type="button">暂停</button>
          {["G1", "G6"].includes(gate.gate_type) ? (
            <button className="danger-button" disabled={disabled} onClick={onKillRequest} type="button">终止项目</button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function PermissionConversationCard({
  disabled,
  onDecision,
}: {
  disabled: boolean;
  onDecision: (decision: "allow" | "deny") => void;
}) {
  return (
    <article className="permission-card conversation-control">
      <div className="control-card-heading">
        <div>
          <span className="control-kind">需要你选择 · 本次搜索</span>
          <strong>是否允许 AI PM 进行这一次网络搜索？</strong>
        </div>
      </div>
      <p>这次搜索用于查找市场、用户和竞品的公开资料，可能使用你配置的搜索账户额度。</p>
      <div className="button-row">
        <button className="primary-button" disabled={disabled} onClick={() => onDecision("allow")} type="button">仅本次允许</button>
        <button disabled={disabled} onClick={() => onDecision("deny")} type="button">拒绝</button>
      </div>
      <small>这个选择只影响这一次搜索，不会替你确认进入下一阶段。</small>
    </article>
  );
}

export function WorkspaceClient({
  initialProject,
  initialMessages,
  initialEvents,
  initialGraph,
  initialGates,
  initialPermissions,
}: {
  initialProject: Project;
  initialMessages: Message[];
  initialEvents: ProjectEvent[];
  initialGraph: ArtifactGraph;
  initialGates: GateRequest[];
  initialPermissions: PermissionRequest[];
}) {
  const router = useRouter();
  const [project, setProject] = useState(initialProject);
  const [messages, setMessages] = useState(initialMessages);
  const [events, setEvents] = useState(initialEvents);
  const [graph, setGraph] = useState(initialGraph);
  const [gates, setGates] = useState(initialGates);
  const [permissions, setPermissions] = useState(initialPermissions);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [decisionPending, setDecisionPending] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState("");
  const [gateComments, setGateComments] = useState<Record<string, string>>({});
  const [confirmingGateId, setConfirmingGateId] = useState<string | null>(null);
  const [connection, setConnection] = useState<"live" | "stale">("live");
  const [mobileView, setMobileView] = useState<"chat" | "artifacts">("chat");
  const [referencedArtifact, setReferencedArtifact] = useState<ArtifactNode | null>(null);
  const [stageFocus, setStageFocus] = useState<{ requestId: number; states: string[] } | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const pendingStageChatEventId = useRef<string | null>(null);
  const autoHandoffAttempted = useRef<Set<string>>(new Set());
  const cursorRef = useRef(events.at(-1)?.sequence ?? 0);

  const timeline = useMemo<TimelineItem[]>(() => {
    const milestoneEvents = events.filter((event) => (
      event.event_type !== "message.created" && isChatMilestoneEvent(event)
    ));
    const processGroups = groupProcessEventsForConversation(events);
    const items: TimelineItem[] = [
      ...messages.map((message) => ({
        type: "message" as const,
        id: message.id,
        createdAt: message.created_at,
        message,
      })),
      ...milestoneEvents
        .map((event) => ({
          type: "event" as const,
          id: event.id,
          createdAt: event.created_at,
          event,
        })),
      ...gates.map((gate) => ({
        type: "gate" as const,
        id: gate.id,
        createdAt: gate.opened_at,
        gate,
      })),
      ...permissions.map((permission) => ({
        type: "permission" as const,
        id: permission.id,
        createdAt: permission.created_at,
        permission,
      })),
      ...processGroups.map((group) => ({
        type: "process" as const,
        id: group.id,
        createdAt: group.events.at(0)?.created_at ?? project.created_at,
        events: group.events,
        label: group.label,
        state: group.state,
      })),
    ];
    return items.sort((left, right) => left.createdAt.localeCompare(right.createdAt));
  }, [events, gates, messages, permissions, project.created_at]);

  const joinedAgents = useMemo(() => {
    const names = events
      .filter((event) => event.event_type === "agent.joined")
      .flatMap((event) => [event.payload.agent_name, event.payload.agent_id])
      .filter((value): value is string => typeof value === "string")
      .map((value) => value.toLowerCase());
    return new Set(names);
  }, [events]);

  function scrollChatToEvent(eventId: string, behavior: ScrollBehavior) {
    const list = messageListRef.current;
    const marker = document.getElementById(`timeline-event-${eventId}`);
    if (!list || !marker) return;
    const listRect = list.getBoundingClientRect();
    const markerRect = marker.getBoundingClientRect();
    list.scrollTo({
      behavior,
      top: list.scrollTop + markerRect.top - listRect.top - 8,
    });
  }

  function showChat() {
    setMobileView("chat");
    const eventId = pendingStageChatEventId.current;
    if (!eventId) return;
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => scrollChatToEvent(eventId, "auto"));
    });
  }

  function focusCompletedStage(states: readonly string[]) {
    const isMobile = window.innerWidth <= 900;
    const eventId = stageStartEventId(events, states);
    if (eventId) {
      pendingStageChatEventId.current = eventId;
      scrollChatToEvent(eventId, isMobile ? "auto" : "smooth");
    }
    setStageFocus((current) => ({
      requestId: (current?.requestId ?? 0) + 1,
      states: [...states],
    }));
    if (isMobile) setMobileView("artifacts");
  }

  useEffect(() => {
    const list = messageListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [timeline.length]);

  useEffect(() => {
    const blocked = [...events].reverse().find((event) => (
      event.event_type === "task.delegation_blocked"
      && typeof event.payload.context_pack_id === "string"
    ));
    const contextPackId = blocked?.payload.context_pack_id;
    if (typeof contextPackId !== "string" || autoHandoffAttempted.current.has(contextPackId)) return;
    const alreadyStarted = events.some((event) => (
      event.event_type === "run.started" && event.payload.context_pack_id === contextPackId
    ));
    if (alreadyStarted) return;
    autoHandoffAttempted.current.add(contextPackId);
    void fetch(
      `/api/control/api/v1/agent-runtime/handoffs/${encodeURIComponent(contextPackId)}/start`,
      { method: "POST" },
    ).catch(() => {
      // The Factory Lead's persisted blocked message remains the user-facing source of truth.
    });
  }, [events]);

  useEffect(() => {
    let active = true;
    let fallbackTimer: number | null = null;
    let reconnectTimer: number | null = null;
    let snapshotTimer: number | null = null;
    let stream: EventSource | null = null;

    function mergeEvents(incoming: ProjectEvent[]) {
      if (!incoming.length) return;
      cursorRef.current = Math.max(
        cursorRef.current,
        ...incoming.map((event) => event.sequence),
      );
      setEvents((current) => {
        const known = new Set(current.map((event) => event.id));
        return [...current, ...incoming.filter((event) => !known.has(event.id))].sort(
          (left, right) => left.sequence - right.sequence,
        );
      });
    }

    async function refreshSnapshot() {
      const [messageResponse, graphResponse, projectResponse, gateResponse, permissionResponse] = await Promise.all([
        fetch(`/api/control/api/v1/projects/${project.id}/messages`, { cache: "no-store" }),
        fetch(`/api/control/api/v1/projects/${project.id}/graph`, { cache: "no-store" }),
        fetch(`/api/control/api/v1/projects/${project.id}`, { cache: "no-store" }),
        fetch(`/api/control/api/v1/projects/${project.id}/gates?status=all`, { cache: "no-store" }),
        fetch(`/api/control/api/v1/projects/${project.id}/permissions`, { cache: "no-store" }),
      ]);
      if (!active) return;
      if ([messageResponse, graphResponse, projectResponse, gateResponse, permissionResponse]
        .some((response) => response.status === 401)) {
        router.push("/");
        router.refresh();
        return;
      }
      if (messageResponse.ok) setMessages((await messageResponse.json()) as Message[]);
      if (graphResponse.ok) setGraph((await graphResponse.json()) as ArtifactGraph);
      if (projectResponse.ok) setProject((await projectResponse.json()) as Project);
      if (gateResponse.ok) setGates((await gateResponse.json()) as GateRequest[]);
      if (permissionResponse.ok) setPermissions((await permissionResponse.json()) as PermissionRequest[]);
    }

    function scheduleSnapshotRefresh() {
      if (snapshotTimer !== null) window.clearTimeout(snapshotTimer);
      snapshotTimer = window.setTimeout(() => {
        snapshotTimer = null;
        void refreshSnapshot().catch(() => setConnection("stale"));
      }, 100);
    }

    async function pollFallback() {
      try {
        const response = await fetch(
          `/api/control/api/v1/projects/${project.id}/events?cursor=${cursorRef.current}`,
          { cache: "no-store" },
        );
        if (response.status === 401) {
          router.push("/");
          router.refresh();
          return;
        }
        if (!response.ok) throw new Error("event fallback failed");
        const incoming = (await response.json()) as ProjectEvent[];
        mergeEvents(incoming);
        if (incoming.length) scheduleSnapshotRefresh();
      } catch {
        if (active) setConnection("stale");
      }
    }

    function startFallback() {
      if (fallbackTimer !== null) return;
      void pollFallback();
      fallbackTimer = window.setInterval(
        () => void pollFallback(),
        eventStreamSync.fallbackIntervalMs,
      );
    }

    function stopFallback() {
      if (fallbackTimer === null) return;
      window.clearInterval(fallbackTimer);
      fallbackTimer = null;
    }

    function connectStream() {
      if (!active) return;
      stream?.close();
      stream = new EventSource(
        `/api/control/api/v1/projects/${project.id}/events/stream?cursor=${cursorRef.current}`,
      );
      stream.addEventListener("open", () => {
        if (!active) return;
        setConnection("live");
        stopFallback();
      });
      stream.addEventListener("ag-ui", (event) => {
        if (!active || !(event instanceof MessageEvent)) return;
        const incoming = parseAgUiProjectEvent(event.data);
        if (!incoming || incoming.project_id !== project.id) return;
        mergeEvents([incoming]);
        scheduleSnapshotRefresh();
      });
      stream.addEventListener("error", () => {
        if (!active) return;
        stream?.close();
        setConnection("stale");
        startFallback();
        if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          connectStream();
        }, 1000);
      });
    }

    connectStream();

    return () => {
      active = false;
      stream?.close();
      stopFallback();
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (snapshotTimer !== null) window.clearTimeout(snapshotTimer);
    };
  }, [project.id, router]);

  function mention(name: string) {
    setDraft((current) => `${current}${current && !current.endsWith(" ") ? " " : ""}@${name} `);
    inputRef.current?.focus();
  }

  function referenceArtifact(artifact: ArtifactNode) {
    setReferencedArtifact(artifact);
    setMobileView("chat");
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }

  function prepareRevision(artifact: ArtifactNode) {
    setReferencedArtifact(artifact);
    setDraft(`@Factory Lead 请基于「${artifact.title}」v${artifact.latest_version} 创建新版本；保留旧版本，不覆盖历史。`);
    setMobileView("chat");
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }

  async function refreshDecisions() {
    const [projectResponse, gateResponse, permissionResponse] = await Promise.all([
      fetch(`/api/control/api/v1/projects/${project.id}`, { cache: "no-store" }),
      fetch(`/api/control/api/v1/projects/${project.id}/gates?status=all`, { cache: "no-store" }),
      fetch(`/api/control/api/v1/projects/${project.id}/permissions`, { cache: "no-store" }),
    ]);
    if (!projectResponse.ok || !gateResponse.ok || !permissionResponse.ok) {
      throw new Error("决定已提交，但刷新控制面快照失败，请刷新页面核对。");
    }
    setProject((await projectResponse.json()) as Project);
    setGates((await gateResponse.json()) as GateRequest[]);
    setPermissions((await permissionResponse.json()) as PermissionRequest[]);
  }

  async function decideGate(
    gate: GateRequest,
    decision: "approve" | "changes" | "pause" | "kill",
  ) {
    const comment = (gateComments[gate.id] ?? "").trim();
    if (decision !== "approve" && !comment) {
      setDecisionError("退回、暂停或终止必须填写理由。");
      return;
    }
    setDecisionPending(`gate:${gate.id}`);
    setDecisionError("");
    try {
      const response = await fetch(`/api/control/api/v1/gates/${gate.id}/decisions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          decision,
          context_version: gate.context_version,
          comment,
        }),
      });
      const body = (await response.json()) as ApiError & {
        handoff_context_pack_id?: string | null;
      };
      if (!response.ok) throw new Error(body.error?.user_message ?? "阶段决定提交失败。");
      if (decision === "approve" && body.handoff_context_pack_id) {
        const handoffResponse = await fetch(
          `/api/control/api/v1/agent-runtime/handoffs/${encodeURIComponent(body.handoff_context_pack_id)}/start`,
          { method: "POST" },
        );
        const handoffBody = (await handoffResponse.json()) as ApiError;
        if (!handoffResponse.ok) {
          throw new Error(handoffBody.error?.user_message ?? "阶段已确认，但下一项任务暂时没能开始。");
        }
      }
      await refreshDecisions();
      setConfirmingGateId(null);
    } catch (reason) {
      setDecisionError(reason instanceof TypeError ? "网络连接失败，阶段决定尚未提交。" : reason instanceof Error ? plainLanguageAgentMessage(reason.message) : "阶段决定提交失败。");
    } finally {
      setDecisionPending(null);
    }
  }

  async function decidePermission(permission: PermissionRequest, decision: "allow" | "deny") {
    setDecisionPending(`permission:${permission.id}`);
    setDecisionError("");
    try {
      const response = await fetch(`/api/control/api/v1/permissions/${permission.id}/decisions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          decision,
          input_hash: permission.input_hash,
        }),
      });
      const body = (await response.json()) as ApiError;
      if (!response.ok) throw new Error(body.error?.user_message ?? "这次选择提交失败。");
      const continuationResponse = await fetch(
        `/api/control/api/v1/agent-runtime/runs/${encodeURIComponent(permission.run_id)}/resume-and-continue`,
        { method: "POST" },
      );
      const continuationBody = (await continuationResponse.json()) as ApiError;
      if (!continuationResponse.ok) {
        throw new Error(continuationBody.error?.user_message ?? "你的选择已记录，但任务暂时没能继续。");
      }
      await refreshDecisions();
    } catch (reason) {
      setDecisionError(reason instanceof TypeError ? "网络连接失败，这次选择尚未提交。" : reason instanceof Error ? plainLanguageAgentMessage(reason.message) : "这次选择提交失败。");
    } finally {
      setDecisionPending(null);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = composeReferencedMessage(draft, referencedArtifact);
    if (!content || pending) return;
    const clientMessageId = crypto.randomUUID();
    setPending(true);
    setError("");
    try {
      const response = await fetch(`/api/control/api/v1/projects/${project.id}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          client_message_id: clientMessageId,
          content,
        }),
      });
      const body = (await response.json()) as Message & ApiError;
      if (!response.ok) throw new Error(body.error?.user_message ?? "消息发送失败，请重试。");
      setMessages((current) => current.some((item) => item.id === body.id) ? current : [...current, body]);
      if (project.state === "alignment") {
        const clarificationResponse = await fetch(
          `/api/control/api/v1/projects/${project.id}/clarifications?context_version=${project.context_version}`,
          { cache: "no-store" },
        );
        const clarifications = clarificationResponse.ok
          ? (await clarificationResponse.json()) as Array<{ id: string; answer: string | null }>
          : [];
        const alignmentResponse = await fetch(
          `/api/control/api/v1/agent-runtime/projects/${project.id}/factory-lead/alignment-runs`,
          {
            method: "POST",
            headers: {
              "content-type": "application/json",
              "idempotency-key": crypto.randomUUID(),
            },
            body: JSON.stringify({
              expected_context_version: project.context_version,
              expected_previous_brief_version: 0,
              client_message_id: clientMessageId,
              content,
              clarification_answers: clarifications
                .filter((item) => item.answer === null)
                .map((item) => ({ clarification_id: item.id, answer: content })),
            }),
          },
        );
        const alignmentBody = (await alignmentResponse.json()) as ApiError;
        if (!alignmentResponse.ok) {
          throw new Error(alignmentBody.error?.user_message ?? "Factory Lead 未能继续处理，请重试。");
        }
      }
      setDraft("");
      setReferencedArtifact(null);
    } catch (reason) {
      setError(reason instanceof TypeError ? "网络连接失败，消息尚未发送，请检查连接后重试。" : reason instanceof Error ? reason.message : "消息发送失败，请重试。");
    } finally {
      setPending(false);
    }
  }

  const currentStage = projectStageIndex(project.state);

  return (
    <main className="workspace-page" id="main-content">
      {connection === "stale" ? (
        <div aria-live="polite" className="reconnect-banner">事件连接暂时中断，保留最后快照并自动重试。</div>
      ) : null}
      <header className="project-header">
        <div>
          <h1><span>项目</span><i aria-hidden="true">/</i>{project.name}</h1>
        </div>
      </header>

      <ol aria-label="项目阶段" className="stage-bar">
        {projectStages.map((stage, index) => {
          const isDone = index < currentStage;
          const content = <><span>{index + 1}</span><div>{stage.displayName ?? stage.name}</div></>;
          return (
            <li className={isDone ? "done" : index === currentStage ? "current" : "future"} key={stage.name}>
              {isDone ? (
                <button
                  aria-label={`定位${stage.name}阶段的群聊和产物`}
                  className="stage-jump"
                  onClick={() => focusCompletedStage(stage.states)}
                  type="button"
                >
                  {content}
                </button>
              ) : <div className="stage-static">{content}</div>}
            </li>
          );
        })}
      </ol>

      <section className={`workspace-grid view-${mobileView}`}>
        <div aria-label="工作区视图" className="mobile-workspace-tabs" role="tablist">
          <button
            aria-controls="chat-workspace-panel"
            aria-selected={mobileView === "chat"}
            onClick={showChat}
            role="tab"
            type="button"
          >
            群聊
            <span>{messages.length}</span>
          </button>
          <button
            aria-controls="artifact-workspace-panel"
            aria-selected={mobileView === "artifacts"}
            onClick={() => setMobileView("artifacts")}
            role="tab"
            type="button"
          >
            产物
            <span>{graph.nodes.length}</span>
          </button>
        </div>

        <div className="chat-panel" id="chat-workspace-panel" role="tabpanel">
          <div aria-label="项目参与者" className="participants">
            <strong className="participants-title">团队群聊</strong>
            <span className="participant participant-user is-present"><span className="presence-dot" />我</span>
            {projectAgentProfiles.map((participant) => {
              const isPresent = participant.aliases.some((alias) => joinedAgents.has(alias));
              return (
                <button
                  aria-label={`${participant.label}，${isPresent ? "已入群" : "未入群"}，点击插入 @${participant.name}`}
                  className={`participant participant-${participant.tone}${isPresent ? " is-present" : ""}`}
                  key={participant.name}
                  onClick={() => mention(participant.name)}
                  title={isPresent ? "已入群" : "Agent 尚未接入"}
                  type="button"
                >
                  <span className="presence-dot" />{participant.label}
                </button>
              );
            })}
          </div>

          <div aria-live="polite" className="message-list" ref={messageListRef}>
            {timeline.length ? timeline.map((item) => {
              if (item.type === "message") {
                return <ConversationMessage key={`message-${item.id}`} message={item.message} />;
              }
              if (item.type === "event") {
                return <ConversationEvent elementId={`timeline-event-${item.id}`} event={item.event} key={`event-${item.id}`} />;
              }
              if (item.type === "gate") {
                const gate = item.gate;
                return (
                  <GateConversationCard
                    comment={gateComments[gate.id] ?? ""}
                    confirmingKill={confirmingGateId === gate.id}
                    disabled={decisionPending !== null}
                    gate={gate}
                    key={`gate-${item.id}`}
                    onComment={(value) => setGateComments((current) => ({ ...current, [gate.id]: value }))}
                    onDecision={(decision) => decideGate(gate, decision)}
                    onKillCancel={() => setConfirmingGateId(null)}
                    onKillRequest={() => {
                      if (!(gateComments[gate.id] ?? "").trim()) {
                        setDecisionError("终止项目必须填写理由。");
                        return;
                      }
                      setDecisionError("");
                      setConfirmingGateId(gate.id);
                    }}
                  />
                );
              }
              if (item.type === "permission") return (
                <PermissionConversationCard
                  disabled={decisionPending !== null}
                  key={`permission-${item.id}`}
                  onDecision={(decision) => decidePermission(item.permission, decision)}
                />
              );
              return <ProcessLedger events={item.events} key={item.id} label={item.label} state={item.state} />;
            }) : (
              <div className="chat-empty"><strong>群聊已就绪</strong><p>发送第一条项目指令。当前只做确定性持久化，不会伪造 Agent 回复。</p></div>
            )}
            {decisionError ? <p className="form-error" role="alert">{decisionError}</p> : null}
          </div>

          <form className="message-composer" onSubmit={sendMessage}>
            <label className="sr-only" htmlFor="message-input">在项目群中发消息</label>
            {referencedArtifact ? (
              <div className="artifact-context" role="status">
                <div>
                  <span>正在引用产物</span>
                  <strong>{referencedArtifact.title} · v{referencedArtifact.latest_version}</strong>
                </div>
                <button aria-label="移除产物引用" onClick={() => setReferencedArtifact(null)} type="button">移除</button>
              </div>
            ) : null}
            <div className="composer-row">
              <textarea
                id="message-input"
                maxLength={50000}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="在项目群中发消息"
                ref={inputRef}
                rows={1}
                value={draft}
              />
              <button className="primary-button" disabled={pending || !draft.trim()} type="submit">
                {pending ? "发送中…" : "发送"}
              </button>
            </div>
            {error ? <p className="form-error">{error}</p> : null}
          </form>
        </div>

        <div className="dag-panel" id="artifact-workspace-panel" role="tabpanel">
          <div className="panel-heading">
            <h2 title={project.name}>{artifactPanelTitle(project)}</h2>
          </div>
          <ArtifactDag
            focusStage={stageFocus}
            graph={graph}
            onPrepareRevision={prepareRevision}
            onReferenceArtifact={referenceArtifact}
            referencedArtifactId={referencedArtifact?.id ?? null}
          />
        </div>
      </section>
    </main>
  );
}
