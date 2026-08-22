"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Project } from "@/lib/contracts";
import {
  formatProjectActivity,
  projectFilter,
  projectNextAction,
  type ProjectAttention,
  type ProjectFilter,
} from "@/lib/home";
import { projectStageIndex, projectStageLabel } from "@/lib/stages";

const filters: { id: ProjectFilter | "all"; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "active", label: "进行中" },
  { id: "waiting", label: "等待我" },
  { id: "paused", label: "暂停" },
  { id: "completed", label: "已完成" },
];

export function ProjectDashboard({
  attention,
  projects,
}: {
  attention: ProjectAttention[];
  projects: Project[];
}) {
  const [filter, setFilter] = useState<ProjectFilter | "all">("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"updated" | "name" | "stage">("updated");
  const [page, setPage] = useState(1);
  const searchInput = useRef<HTMLInputElement>(null);
  const attentionByProject = useMemo(() => new Map(attention.map((item) => [item.projectId, item])), [attention]);
  const waitingItems = attention.flatMap((item) => item.items.map((detail) => ({ ...detail, projectId: item.projectId })));

  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) return;
      event.preventDefault();
      searchInput.current?.focus();
    }
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  const counts = useMemo(() => {
    const result: Record<ProjectFilter, number> = { active: 0, waiting: 0, paused: 0, completed: 0 };
    projects.forEach((project) => {
      const item = attentionByProject.get(project.id) ?? { projectId: project.id, items: [], unavailable: true };
      result[projectFilter(project, item)] += 1;
    });
    return result;
  }, [attentionByProject, projects]);

  const filtered = useMemo(() => projects
    .filter((project) => {
      const item = attentionByProject.get(project.id) ?? { projectId: project.id, items: [], unavailable: true };
      const matchesFilter = filter === "all" || projectFilter(project, item) === filter;
      return matchesFilter && project.name.toLocaleLowerCase("zh-CN").includes(query.trim().toLocaleLowerCase("zh-CN"));
    })
    .sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name, "zh-CN");
      if (sort === "stage") return projectStageIndex(a.state) - projectStageIndex(b.state);
      return b.updated_at.localeCompare(a.updated_at);
    }), [attentionByProject, filter, projects, query, sort]);

  const pageSize = 6;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <>
      <section aria-labelledby="attention-title" className={`attention-summary${waitingItems.length ? " has-items" : ""}`}>
        <div>
          <p className="eyebrow">MY ATTENTION / 真实控制面</p>
          <h2 id="attention-title">等待我处理 <span>{waitingItems.length}</span></h2>
          <p>{waitingItems.length ? "Gate 与一次性 Permission 分开统计，点击项目进入原始决策卡。" : "当前没有真实开放的 Gate 或 PermissionRequest。"}</p>
        </div>
        {waitingItems.length ? (
          <div className="attention-links">
            {waitingItems.slice(0, 3).map((item) => {
              const project = projects.find((candidate) => candidate.id === item.projectId);
              return (
                <Link href={`/projects/${item.projectId}`} key={`${item.kind}-${item.id}`}>
                  <span>{item.kind === "gate" ? "GATE" : "PERMISSION"}</span>
                  <strong>{item.label}</strong>
                  <small>{project?.name ?? "项目"}</small>
                </Link>
              );
            })}
          </div>
        ) : null}
      </section>

      <section aria-labelledby="projects-title" className="workshop-panel projects-panel" id="projects" tabIndex={-1}>
        <header className="workshop-panel-title">
          <h2 id="projects-title">真实项目</h2>
          <span>{projects.length} 个项目</span>
        </header>
        <div className="project-controls">
          <div aria-label="项目状态筛选" className="project-filters" role="group">
            {filters.map((item) => {
              const count = item.id === "all" ? projects.length : counts[item.id];
              return (
                <button aria-pressed={filter === item.id} key={item.id} onClick={() => { setFilter(item.id); setPage(1); }} type="button">
                  {item.label}<span>{count}</span>
                </button>
              );
            })}
          </div>
          <div className="project-query-controls">
            <label>
              <span className="sr-only">搜索项目</span>
              <input aria-keyshortcuts="/" onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索项目 /" ref={searchInput} type="search" value={query} />
            </label>
            <label>
              <span className="sr-only">项目排序</span>
              <select onChange={(event) => { setSort(event.target.value as typeof sort); setPage(1); }} value={sort}>
                <option value="updated">最近更新</option>
                <option value="name">项目名称</option>
                <option value="stage">项目阶段</option>
              </select>
            </label>
          </div>
        </div>
        {visible.length ? (
          <div className="project-list" aria-live="polite">
            <div aria-hidden="true" className="project-table-head">
              <span>项目名称</span><span>阶段 / 状态</span><span>最后活动</span><span>下一步</span><span>操作</span>
            </div>
            {visible.map((project) => {
              const projectAttentionItem = attentionByProject.get(project.id) ?? { projectId: project.id, items: [], unavailable: true };
              const category = projectFilter(project, projectAttentionItem);
              return (
                <article className="project-row" key={project.id}>
                  <div className="project-name-cell">
                    <span aria-hidden="true" className="project-swatch" />
                    <div><strong>{project.name}</strong><small>Context v{project.context_version}</small></div>
                  </div>
                  <span className="stage-label"><b>{Math.max(1, projectStageIndex(project.state) + 1)}</b><span>{projectStageLabel(project.state)}<small>{category === "waiting" ? `等待我 · ${projectAttentionItem.items.length}` : category === "active" ? "进行中" : category === "paused" ? "已暂停" : "已完成"}</small></span></span>
                  <time dateTime={project.updated_at}>{formatProjectActivity(project.updated_at)}</time>
                  <span className="project-next-action">{projectNextAction(project, projectAttentionItem)}</span>
                  <Link className="primary-link" href={`/projects/${project.id}`}>{category === "waiting" ? "去处理" : "继续项目"}</Link>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">
            <strong>没有匹配的项目</strong>
            <p>调整筛选或搜索词。系统不会用示例项目填充结果。</p>
          </div>
        )}
        {filtered.length > pageSize ? (
          <nav aria-label="项目分页" className="project-pagination">
            <button disabled={currentPage <= 1} onClick={() => setPage((value) => value - 1)} type="button">上一页</button>
            <span>第 {currentPage} / {totalPages} 页</span>
            <button disabled={currentPage >= totalPages} onClick={() => setPage((value) => value + 1)} type="button">下一页</button>
          </nav>
        ) : null}
      </section>
    </>
  );
}
