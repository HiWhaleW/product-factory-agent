import { NewProjectForm } from "@/app/new-project-form";
import { ProjectDashboard } from "@/app/project-dashboard";
import { getGates, getHealth, getPermissions, getProjects } from "@/lib/api";
import { projectAttention, type ProjectAttention } from "@/lib/home";

export const dynamic = "force-dynamic";

export default async function ProjectListPage() {
  const [projects, health] = await Promise.all([getProjects(), getHealth()]);
  const attention = await Promise.all(projects.map(async (project): Promise<ProjectAttention> => {
    try {
      const [gates, permissions] = await Promise.all([getGates(project.id), getPermissions(project.id)]);
      return projectAttention(project.id, gates, permissions);
    } catch {
      return { projectId: project.id, items: [], unavailable: true };
    }
  }));

  return (
    <main className="page-shell home-page" id="main-content">
      <section className="home-hero">
        <p className="eyebrow">PRODUCT WORKSHOP / REAL CONTROL PLANE</p>
        <h1>从一个真实想法，建立可追溯的产品交付链</h1>
      </section>

      <section aria-labelledby="create-title" className="workshop-panel create-project-panel">
        <header className="workshop-panel-title"><span>NEW PROJECT</span><span>/</span><span>项目对齐</span></header>
        <div aria-label="新项目流程" className="creation-flow">
          <div><strong>01</strong><span>说清一个真实想法</span></div>
          <div><strong>02</strong><span>形成 Project Brief</span></div>
          <div><strong>03</strong><span>G0 批准后进入 MRD</span></div>
        </div>
        <p className="creation-note">当前只创建项目并持久化输入，不伪造 Agent 回复</p>
        <NewProjectForm />
        <footer aria-label="运行状态" className="runtime-strip">
          <span className={health.status === "ok" ? "runtime-item is-online" : "runtime-item is-error"}>DATABASE {health.status === "ok" ? "CONNECTED" : "ERROR"}</span>
          <strong>{health.database.toUpperCase()}</strong>
          <span className="runtime-item is-offline">AGENT OFFLINE</span>
        </footer>
      </section>

      <ProjectDashboard attention={attention} projects={projects} />
    </main>
  );
}
