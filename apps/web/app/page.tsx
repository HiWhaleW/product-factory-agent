import Link from "next/link";

import { NewProjectForm } from "@/app/new-project-form";
import { getHealth, getProjects } from "@/lib/api";
import { projectStageIndex, projectStageLabel } from "@/lib/stages";

export const dynamic = "force-dynamic";

export default async function ProjectListPage() {
  const [projects, health] = await Promise.all([getProjects(), getHealth()]);

  return (
    <main className="page-shell home-page">
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

      <section aria-labelledby="projects-title" className="workshop-panel projects-panel">
        <header className="workshop-panel-title">
          <h2 id="projects-title">真实项目</h2>
          <span>{projects.length} 个项目</span>
        </header>
        {projects.length ? (
          <div className="project-list">
            <div aria-hidden="true" className="project-table-head">
              <span>项目名称</span><span>项目阶段</span><span>Context</span><span>数据库事实</span><span>操作</span>
            </div>
            {projects.map((project) => (
              <article className="project-row" key={project.id}>
                <div className="project-name-cell">
                  <span aria-hidden="true" className="project-swatch" />
                  <strong>{project.name}</strong>
                </div>
                <span className="stage-label"><b>{Math.max(1, projectStageIndex(project.state) + 1)}</b>{projectStageLabel(project.state)}</span>
                <span>Context v{project.context_version}</span>
                <span className="database-fact"><i aria-hidden="true" />已连接</span>
                <Link className="primary-link" href={`/projects/${project.id}`}>
                  继续项目
                </Link>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <strong>还没有项目</strong>
            <p>在上方输入一个真实想法。创建后进入项目对齐阶段，G0 前不会自动拉入 AI PM。</p>
          </div>
        )}
      </section>
    </main>
  );
}
