import { LoginForm } from "@/app/login-form";
import { NewProjectForm } from "@/app/new-project-form";
import { ProjectDashboard } from "@/app/project-dashboard";
import { getGates, getHealth, getMe, getPermissions, getProjects } from "@/lib/api";
import { projectAttention, type ProjectAttention } from "@/lib/home";

export const dynamic = "force-dynamic";

export default async function ProjectListPage() {
  const [session, health] = await Promise.all([getMe(), getHealth()]);
  if (session.auth_enforced && !session.authenticated) {
    return (
      <main className="page-shell home-page auth-page" id="main-content">
        <section className="home-hero"><p className="eyebrow">PROJECTS / AUTHENTICATION REQUIRED</p><h1>登录后查看你的真实项目</h1></section>
        <section className="workshop-panel auth-panel" aria-label="登录"><LoginForm /></section>
      </main>
    );
  }
  const projects = await getProjects();
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
      <section className="home-hero"><p className="eyebrow">REAL PROJECTS / 真实项目</p><h1>你的项目交付链</h1></section>
      <section aria-label="创建项目" className="workshop-panel create-project-panel">
        <header className="workshop-panel-title"><span>NEW PROJECT</span><span>/</span><span>项目对齐</span></header>
        <div aria-label="新项目流程" className="creation-flow">
          <div><strong>01</strong><span>说清一个真实想法</span></div><div><strong>02</strong><span>形成 Project Brief</span></div><div><strong>03</strong><span>G0 批准后进入 MRD</span></div>
        </div>
        <p className="creation-note">当前只创建项目并持久化输入，不伪造 Agent 回复</p>
        <NewProjectForm />
        <footer aria-label="运行状态" className="runtime-strip">
          <span className={health.status === "ok" ? "runtime-item is-online" : "runtime-item is-error"}>DATABASE {health.status === "ok" ? "CONNECTED" : "ERROR"}</span>
          <strong>{health.database.toUpperCase()}</strong><span className="runtime-item is-offline">AGENT OFFLINE</span>
        </footer>
      </section>
      <ProjectDashboard attention={attention} projects={projects} />
    </main>
  );
}
