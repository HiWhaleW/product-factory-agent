"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useRef, useState } from "react";

import type { ApiError, Project } from "@/lib/contracts";

export function NewProjectForm() {
  const router = useRouter();
  const attempt = useRef<{
    name: string;
    projectKey: string;
    messageKey: string;
    runKey: string;
  } | null>(null);
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = name.trim();
    if (!normalized || pending) return;
    setPending(true);
    setError("");
    if (!attempt.current || attempt.current.name !== normalized) {
      attempt.current = {
        name: normalized,
        projectKey: crypto.randomUUID(),
        messageKey: crypto.randomUUID(),
        runKey: crypto.randomUUID(),
      };
    }
    try {
      const response = await fetch("/api/control/api/v1/projects", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "idempotency-key": attempt.current.projectKey,
        },
        body: JSON.stringify({
          name: normalized,
          initial_goal: normalized,
          initial_message_id: attempt.current.messageKey,
        }),
      });
      const body = (await response.json()) as Project & ApiError;
      if (!response.ok) throw new Error(body.error?.user_message ?? "项目创建失败，请重试。");
      const alignmentResponse = await fetch(
        `/api/control/api/v1/agent-runtime/projects/${body.id}/factory-lead/alignment-runs`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "idempotency-key": attempt.current.runKey,
          },
          body: JSON.stringify({
            expected_context_version: body.context_version,
            expected_previous_brief_version: 0,
            client_message_id: attempt.current.messageKey,
            content: normalized,
            clarification_answers: [],
          }),
        },
      );
      const alignmentBody = (await alignmentResponse.json()) as ApiError;
      if (!alignmentResponse.ok) {
        throw new Error(alignmentBody.error?.user_message ?? "项目已创建，但 Factory Lead 启动失败，请重试。");
      }
      router.push(`/projects/${body.id}`);
      router.refresh();
    } catch (reason) {
      setError(reason instanceof TypeError ? "网络连接失败，项目尚未创建，请检查连接后重试。" : reason instanceof Error ? reason.message : "项目创建失败，请重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="idea-composer" onSubmit={submit}>
      <label className="idea-label" htmlFor="project-idea">
        <strong id="create-title">你想做什么产品？</strong>
        <span>产品想法或项目名称</span>
      </label>
      <textarea
        id="project-idea"
        maxLength={200}
        onChange={(event) => setName(event.target.value)}
        placeholder="例如：帮销售团队自动整理访谈、生成复盘报告"
        required
        rows={3}
        value={name}
      />
      <button className="primary-button" disabled={pending} type="submit">
        {pending ? "正在创建并启动 Agent…" : "创建项目"}
      </button>
      {error ? <p aria-live="polite" className="form-error">{error}</p> : null}
    </form>
  );
}
