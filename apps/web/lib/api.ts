import "server-only";

import { cookies } from "next/headers";

import type {
  ArtifactContent,
  ArtifactGraph,
  GateRequest,
  Message,
  PermissionRequest,
  ProviderCredentialStatus,
  Project,
  ProjectEvent,
  RuntimeStatus,
  SessionStatus,
} from "@/lib/contracts";

const apiBaseUrl = process.env.PRODUCT_FACTORY_API_URL ?? "http://127.0.0.1:8000";

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function apiFetch<T>(path: string): Promise<T> {
  const cookieHeader = (await cookies()).toString();
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
  if (!response.ok) {
    let message = `API request failed (${response.status})`;
    try {
      const body = (await response.json()) as { error?: { user_message?: string } };
      message = body.error?.user_message ?? message;
    } catch {
      // Keep the safe status-only fallback when the upstream body is not JSON.
    }
    throw new ApiRequestError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const getProjects = () => apiFetch<Project[]>("/api/v1/projects");
export const getProject = (projectId: string) =>
  apiFetch<Project>(`/api/v1/projects/${encodeURIComponent(projectId)}`);
export const getMessages = (projectId: string) =>
  apiFetch<Message[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/messages`);
export async function getEvents(projectId: string) {
  const encodedProjectId = encodeURIComponent(projectId);
  const events: ProjectEvent[] = [];
  let cursor = 0;
  while (true) {
    const page = await apiFetch<ProjectEvent[]>(
      `/api/v1/projects/${encodedProjectId}/events?cursor=${cursor}&limit=500`,
    );
    events.push(...page);
    if (page.length < 500) return events;
    cursor = page.at(-1)?.sequence ?? cursor;
  }
}
export const getGraph = (projectId: string) =>
  apiFetch<ArtifactGraph>(`/api/v1/projects/${encodeURIComponent(projectId)}/graph`);
export const getGates = (projectId: string, status: "open" | "all" = "open") =>
  apiFetch<GateRequest[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/gates?status=${status}`,
  );
export const getPermissions = (projectId: string) =>
  apiFetch<PermissionRequest[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/permissions`);
export const getHealth = () =>
  apiFetch<{
    status: string;
    database: string;
    model_provider: string;
    model_configured: boolean;
  }>("/health");
export const getRuntimeStatus = () => apiFetch<RuntimeStatus>("/api/v1/runtime/status");
export const getMe = () => apiFetch<SessionStatus>("/api/v1/me");
export const getProviderCredential = () =>
  apiFetch<ProviderCredentialStatus>("/api/v1/me/provider-credentials/model-api");
export const getArtifactContent = (artifactId: string, version?: number) =>
  apiFetch<ArtifactContent>(
    `/api/v1/artifacts/${encodeURIComponent(artifactId)}/content${version ? `?version=${version}` : ""}`,
  );
