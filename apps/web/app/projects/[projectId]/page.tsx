import { notFound } from "next/navigation";

import { WorkspaceClient } from "@/app/projects/[projectId]/workspace-client";
import {
  ApiRequestError,
  getEvents,
  getGates,
  getGraph,
  getMessages,
  getPermissions,
  getProject,
} from "@/lib/api";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ projectId: string }> };

async function loadWorkspace(projectId: string) {
  try {
    return await Promise.all([
      getProject(projectId),
      getMessages(projectId),
      getEvents(projectId),
      getGraph(projectId),
      getGates(projectId, "all"),
      getPermissions(projectId),
    ]);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) notFound();
    throw error;
  }
}

export default async function ProjectWorkspacePage({ params }: Props) {
  const { projectId } = await params;
  const [project, messages, events, graph, gates, permissions] = await loadWorkspace(projectId);
  return (
    <WorkspaceClient
      initialEvents={events}
      initialGates={gates}
      initialGraph={graph}
      initialMessages={messages}
      initialPermissions={permissions}
      initialProject={project}
    />
  );
}
