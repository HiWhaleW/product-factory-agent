"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
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
import { projectStageIndex, projectStageLabel, projectStages } from "@/lib/stages";
import { localUser } from "@/lib/identity";
import {
  composeReferencedMessage,
  cursorPollingSync,
  eventPresentation,
  formatProjectVersion,
  parseReferencedMessage,
} from "@/lib/workspace";

const ArtifactDag = dynamic(
  () => import("@/app/projects/[projectId]/artifact-dag").then((module) => module.ArtifactDag),
  { ssr: false, loading: () => <div className="dag-loading">正在载入产物画布…</div> },
);

const participantRoster = [
  { name: "Factory Lead", label: "主 Agent", avatar: "主", tone: "lead", aliases: ["factory lead", "factory-lead", "factory_lead"] },
  { name: "AI PM", label: "AI PM", avatar: "PM", tone: "pm", aliases: ["ai pm", "ai-pm", "ai_pm"] },
  { name: "Builder", label: "Builder", avatar: "建", tone: "builder", aliases: ["builder"] },
  { name: "Reviewer", label: "Reviewer", avatar: "审", tone: "reviewer", aliases: ["reviewer"] },
] as const;
const timeFormatter = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" });
const dateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatTime(value: string) {
  return timeFormatter.format(new Date(value));
}

type TimelineItem =
  | { type: "message"; id: string; createdAt: string; message: Message }
  | { type: "event"; id: string; createdAt: string; event: ProjectEvent }
  | { type: "gate"; id: string; createdAt: string; gate: GateRequest }
  | { type: "permission"; id: string; createdAt: string; permission: PermissionRequest };

function messageIdentity(message: Message) {
  if (message.actor_type === "user") {
    return { avatar: "我", label: "你", tone: "user" };
  }
  const actorId = message.actor_id.toLowerCase();
  const participant = participantRoster.find((item) => (
    item.aliases.some((alias) => actorId === alias || actorId.includes(alias))
  ));
  return participant
    ? { avatar: participant.avatar, label: participant.label, tone: participant.name.toLowerCase().replace(" ", "-") }
    : { avatar: "A", label: message.actor_id || "Agent", tone: "agent" };
}

function ConversationMessage({ message }: { message: Message }) {
  const identity = messageIdentity(message);
  const content = parseReferencedMessage(message.content);
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
          {content.body ? <p>{content.body}</p> : null}
        </div>
      </div>
    </article>
  );
}

function ConversationEvent({ event }: { event: ProjectEvent }) {
  const presentation = eventPresentation(event);
  if (presentation.tone === "agent") {
    return (
      <article className="conversation-narration">
        <span aria-hidden="true" />
        <p>{presentation.summary}</p>
        <span aria-hidden="true" />
      </article>
    );
  }
  const iconSrc = event.event_type.startsWith("artifact.")
    ? "/icon-artifact-event.png"
    : event.event_type.startsWith("gate.") || event.event_type.startsWith("permission.")
      ? "/icon-gate-event.png"
      : "/icon-project-event.png";
  return (
    <article className={`conversation-event tone-${presentation.tone}`}>
      <Image alt="" className="conversation-event-icon" height={42} src={iconSrc} width={42} />
      <strong>{presentation.label}</strong>
      <p>{presentation.summary}</p>
      <time>{formatTime(event.created_at)}</time>
    </article>
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
          <span className="control-kind">{isOpen ? "需要你选择" : "历史记录"} · 产品闸口 {gate.gate_type}</span>
          <strong>是否进入 {gate.target_state ? projectStageLabel(gate.target_state) : "既定下一阶段"}？</strong>
        </div>
        <span>Context v{gate.context_version}</span>
      </div>
      <p>{isOpen
        ? "这是不可变的产品阶段决定，不能由普通群聊代替。"
        : `该 Gate 已记录为 ${gate.status}；这里只读展示当时的审批依据与已知问题。`}</p>
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
  permission,
}: {
  disabled: boolean;
  onDecision: (decision: "allow" | "deny") => void;
  permission: PermissionRequest;
}) {
  return (
    <article className="permission-card conversation-control">
      <div className="control-card-heading">
        <div>
          <span className="control-kind">需要你选择 · 一次性工具权限</span>
          <strong>是否允许 {permission.tool_name}？</strong>
        </div>
        <span>{permission.risk_level}</span>
      </div>
      <p>Task {permission.task_id.slice(0, 8)} · Context v{permission.context_version} · input {permission.input_hash.slice(0, 8)}…</p>
      <p>{permission.reason || "后端未提供权限原因。"}</p>
      <p>{permission.expires_at ? `有效期至 ${dateTimeFormatter.format(new Date(permission.expires_at))}` : "未设置有效期"}；脱敏参数 {JSON.stringify(permission.redacted_parameters)}</p>
      <div className="button-row">
        <button className="primary-button" disabled={disabled} onClick={() => onDecision("allow")} type="button">仅本次允许</button>
        <button disabled={disabled} onClick={() => onDecision("deny")} type="button">拒绝</button>
      </div>
      <small>Permission 只授权这次工具输入，绝不推进产品阶段。</small>
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
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const cursor = events.at(-1)?.sequence ?? 0;

  const timeline = useMemo<TimelineItem[]>(() => {
    const items: TimelineItem[] = [
      ...messages.map((message) => ({
        type: "message" as const,
        id: message.id,
        createdAt: message.created_at,
        message,
      })),
      ...events
        .filter((event) => event.event_type !== "message.created")
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
    ];
    return items.sort((left, right) => left.createdAt.localeCompare(right.createdAt));
  }, [events, gates, messages, permissions]);

  const joinedAgents = useMemo(() => {
    const names = events
      .filter((event) => event.event_type === "agent.joined")
      .flatMap((event) => [event.payload.agent_name, event.payload.agent_id])
      .filter((value): value is string => typeof value === "string")
      .map((value) => value.toLowerCase());
    return new Set(names);
  }, [events]);

  useEffect(() => {
    const list = messageListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [timeline.length]);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(
          `/api/control/api/v1/projects/${project.id}/events?cursor=${cursor}`,
          { cache: "no-store" },
        );
        if (!response.ok) throw new Error("event poll failed");
        const incoming = (await response.json()) as ProjectEvent[];
        if (incoming.length) {
          setEvents((current) => {
            const known = new Set(current.map((event) => event.id));
            return [...current, ...incoming.filter((event) => !known.has(event.id))].sort(
              (left, right) => left.sequence - right.sequence,
            );
          });
          const [messageResponse, graphResponse, projectResponse, gateResponse, permissionResponse] = await Promise.all([
            fetch(`/api/control/api/v1/projects/${project.id}/messages`, { cache: "no-store" }),
            fetch(`/api/control/api/v1/projects/${project.id}/graph`, { cache: "no-store" }),
            fetch(`/api/control/api/v1/projects/${project.id}`, { cache: "no-store" }),
            fetch(`/api/control/api/v1/projects/${project.id}/gates?status=all`, { cache: "no-store" }),
            fetch(`/api/control/api/v1/projects/${project.id}/permissions`, { cache: "no-store" }),
          ]);
          if (messageResponse.ok) setMessages((await messageResponse.json()) as Message[]);
          if (graphResponse.ok) setGraph((await graphResponse.json()) as ArtifactGraph);
          if (projectResponse.ok) setProject((await projectResponse.json()) as Project);
          if (gateResponse.ok) setGates((await gateResponse.json()) as GateRequest[]);
          if (permissionResponse.ok) setPermissions((await permissionResponse.json()) as PermissionRequest[]);
        }
        setConnection("live");
      } catch {
        setConnection("stale");
      }
    }, cursorPollingSync.intervalMs);
    return () => window.clearInterval(timer);
  }, [cursor, project.id]);

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
          decided_by: localUser.id,
        }),
      });
      const body = (await response.json()) as ApiError;
      if (!response.ok) throw new Error(body.error?.user_message ?? "Gate 决定提交失败。");
      await refreshDecisions();
      setConfirmingGateId(null);
    } catch (reason) {
      setDecisionError(reason instanceof TypeError ? "网络连接失败，Gate 决定尚未提交。" : reason instanceof Error ? reason.message : "Gate 决定提交失败。");
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
          decided_by: localUser.id,
        }),
      });
      const body = (await response.json()) as ApiError;
      if (!response.ok) throw new Error(body.error?.user_message ?? "Permission 决定提交失败。");
      await refreshDecisions();
    } catch (reason) {
      setDecisionError(reason instanceof TypeError ? "网络连接失败，Permission 决定尚未提交。" : reason instanceof Error ? reason.message : "Permission 决定提交失败。");
    } finally {
      setDecisionPending(null);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = composeReferencedMessage(draft, referencedArtifact);
    if (!content || pending) return;
    setPending(true);
    setError("");
    try {
      const response = await fetch(`/api/control/api/v1/projects/${project.id}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          client_message_id: crypto.randomUUID(),
          content,
          actor_id: localUser.id,
        }),
      });
      const body = (await response.json()) as Message & ApiError;
      if (!response.ok) throw new Error(body.error?.user_message ?? "消息发送失败，请重试。");
      setMessages((current) => current.some((item) => item.id === body.id) ? current : [...current, body]);
      setDraft("");
      setReferencedArtifact(null);
    } catch (reason) {
      setError(reason instanceof TypeError ? "网络连接失败，消息尚未发送，请检查连接后重试。" : reason instanceof Error ? reason.message : "消息发送失败，请重试。");
    } finally {
      setPending(false);
    }
  }

  const currentStage = projectStageIndex(project.state);
  const projectVersion = formatProjectVersion(project.context_version);

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
        {projectStages.map((stage, index) => (
          <li className={index < currentStage ? "done" : index === currentStage ? "current" : "future"} key={stage.name}>
            <span>{index + 1}</span>
            <div>{stage.displayName ?? stage.name}</div>
          </li>
        ))}
      </ol>

      <section className={`workspace-grid view-${mobileView}`}>
        <div aria-label="工作区视图" className="mobile-workspace-tabs" role="tablist">
          <button
            aria-controls="chat-workspace-panel"
            aria-selected={mobileView === "chat"}
            onClick={() => setMobileView("chat")}
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
            {participantRoster.map((participant) => {
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
                return <ConversationEvent event={item.event} key={`event-${item.id}`} />;
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
              return (
                <PermissionConversationCard
                  disabled={decisionPending !== null}
                  key={`permission-${item.id}`}
                  onDecision={(decision) => decidePermission(item.permission, decision)}
                  permission={item.permission}
                />
              );
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
            <h2>{projectStageLabel(project.state)} {projectVersion}</h2>
          </div>
          <ArtifactDag
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
