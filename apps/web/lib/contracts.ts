export type Project = {
  id: string;
  owner_user_id: string;
  name: string;
  state: string;
  context_version: number;
  iteration_version: number;
  created_at: string;
  updated_at: string;
};

export type DeletedProject = Project & {
  deleted_at: string;
};

export type Message = {
  id: string;
  project_id: string;
  client_message_id: string;
  actor_type: string;
  actor_id: string;
  content: string;
  created_at: string;
};

export type ProjectEvent = {
  id: string;
  project_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type GateRequest = {
  id: string;
  project_id: string;
  gate_type: string;
  context_version: number;
  status: string;
  target_state: string | null;
  reason: string;
  impacted_artifact_refs: Array<{
    artifact_id: string;
    version: number;
  }>;
  known_issues: Array<{
    issue: string;
    severity: "P0" | "P1" | "P2";
    evidence_refs: string[];
    source_refs: Array<Record<string, unknown>>;
    status: "open" | "resolved" | "accepted";
  }>;
  opened_at: string;
};

export type PermissionRequest = {
  id: string;
  project_id: string;
  task_id: string;
  run_id: string;
  tool_name: string;
  input_hash: string;
  risk_level: string;
  reason: string;
  redacted_parameters: Record<string, unknown>;
  context_version: number;
  status: string;
  expires_at: string | null;
  created_at: string;
};

export type ArtifactNode = {
  id: string;
  title: string;
  kind: string;
  stage: string;
  status: string;
  latest_version: number;
  owner_agent: string;
  created_at: string;
};

export type ArtifactEdge = {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
};

export type ArtifactGraph = {
  nodes: ArtifactNode[];
  edges: ArtifactEdge[];
};

export type ArtifactContent = {
  artifact_id: string;
  version: number;
  title: string;
  filename: string;
  content_type: string;
  content: string;
};

export type ArtifactVersionIndex = {
  artifact_id: string;
  version: number;
  context_version: number;
  approval_status: string;
  content_hash: string;
  summary: string;
  created_by: string;
  created_at: string;
  content_available: boolean;
};

export type RuntimeStatus = {
  database: string;
  artifact_root_configured: boolean;
  workspace_root_configured: boolean;
  model_provider: string;
  model_configured: boolean;
  event_transport: "ag_ui_sse";
  short_polling_degraded: boolean;
  builder_enabled: boolean;
  codex: {
    configured: boolean;
    executable: boolean;
    version: string | null;
    exit_code: number | null;
    checked_at: string;
    error: string | null;
  };
};

export type SessionStatus = {
  authenticated: boolean;
  user_id: string | null;
  username: string | null;
  display_name: string | null;
  role: "admin" | "user" | null;
  expires_at: string | null;
  reason: "active" | "missing" | "invalid" | "expired" | "auth_not_configured" | "logged_out" | "user_inactive";
  auth_enforced: boolean;
};

export type ProviderCredentialStatus = {
  provider: "openai_compatible";
  configured: boolean;
  provider_name: string | null;
  base_url: string | null;
  model_name: string | null;
  masked_hint: string | null;
  updated_at: string | null;
  internal_test_fallback: boolean;
};

export type ResearchCredentialStatus = {
  provider: "web_search";
  configured: boolean;
  provider_name: string | null;
  base_url: string | null;
  masked_hint: string | null;
  updated_at: string | null;
  runtime_supported: boolean;
};

export type ApiError = {
  error?: {
    code?: string;
    user_message?: string;
    request_id?: string;
  };
};
