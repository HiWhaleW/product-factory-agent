"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ApiError, DeletedProject, Project } from "@/lib/contracts";
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
  const router = useRouter();
  const [removedProjectIds, setRemovedProjectIds] = useState<Set<string>>(() => new Set());
  const [view, setView] = useState<"projects" | "trash">("projects");
  const [trashProjects, setTrashProjects] = useState<DeletedProject[]>([]);
  const [trashLoaded, setTrashLoaded] = useState(false);
  const [trashLoading, setTrashLoading] = useState(false);
  const [restoringProjectId, setRestoringProjectId] = useState<string | null>(null);
  const [filter, setFilter] = useState<ProjectFilter | "all">("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"updated" | "name" | "stage">("updated");
  const [page, setPage] = useState(1);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [deleteStatus, setDeleteStatus] = useState("");
  const [deleteStatusIsError, setDeleteStatusIsError] = useState(false);
  const searchInput = useRef<HTMLInputElement>(null);
  const projectItems = useMemo(
    () => projects.filter((project) => !removedProjectIds.has(project.id)),
    [projects, removedProjectIds],
  );
  const attentionByProject = useMemo(() => new Map(attention.map((item) => [item.projectId, item])), [attention]);
  const projectIds = useMemo(() => new Set(projectItems.map((project) => project.id)), [projectItems]);
  const waitingItems = attention
    .filter((item) => projectIds.has(item.projectId))
    .flatMap((item) => item.items.map((detail) => ({ ...detail, projectId: item.projectId })));

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
    projectItems.forEach((project) => {
      const item = attentionByProject.get(project.id) ?? { projectId: project.id, items: [], unavailable: true };
      result[projectFilter(project, item)] += 1;
    });
    return result;
  }, [attentionByProject, projectItems]);

  const filtered = useMemo(() => projectItems
    .filter((project) => {
      const item = attentionByProject.get(project.id) ?? { projectId: project.id, items: [], unavailable: true };
      const matchesFilter = filter === "all" || projectFilter(project, item) === filter;
      return matchesFilter && project.name.toLocaleLowerCase("zh-CN").includes(query.trim().toLocaleLowerCase("zh-CN"));
    })
    .sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name, "zh-CN");
      if (sort === "stage") return projectStageIndex(a.state) - projectStageIndex(b.state);
      return b.updated_at.localeCompare(a.updated_at);
    }), [attentionByProject, filter, projectItems, query, sort]);

  async function deleteProject(project: Project) {
    const confirmed = window.confirm(
      `确认删除“${project.name}”？\n\n项目会进入回收箱，可随时恢复；历史执行记录和审计链不会丢失。`,
    );
    if (!confirmed) return;
    setDeletingProjectId(project.id);
    setDeleteStatus("");
    setDeleteStatusIsError(false);
    try {
      const response = await fetch(`/api/control/api/v1/projects/${encodeURIComponent(project.id)}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm_name: project.name }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error?.user_message ?? `删除失败（${response.status}）`);
      }
      setRemovedProjectIds((current) => new Set(current).add(project.id));
      setTrashLoaded(false);
      setDeleteStatus(`已将“${project.name}”移入回收箱。`);
      window.dispatchEvent(new CustomEvent("product-factory:session-changed"));
      router.refresh();
    } catch (error) {
      setDeleteStatusIsError(true);
      setDeleteStatus(error instanceof Error ? error.message : "删除失败，请稍后重试。");
    } finally {
      setDeletingProjectId(null);
    }
  }

  async function loadTrash() {
    setTrashLoading(true);
    setDeleteStatus("");
    setDeleteStatusIsError(false);
    try {
      const response = await fetch("/api/control/api/v1/projects/trash", { cache: "no-store" });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error?.user_message ?? `回收箱加载失败（${response.status}）`);
      }
      setTrashProjects((await response.json()) as DeletedProject[]);
      setTrashLoaded(true);
    } catch (error) {
      setDeleteStatusIsError(true);
      setDeleteStatus(error instanceof Error ? error.message : "回收箱加载失败，请稍后重试。");
    } finally {
      setTrashLoading(false);
    }
  }

  async function toggleTrash() {
    if (view === "trash") {
      setView("projects");
      setDeleteStatus("");
      setDeleteStatusIsError(false);
      return;
    }
    setView("trash");
    if (!trashLoaded) await loadTrash();
  }

  async function restoreProject(project: DeletedProject) {
    setRestoringProjectId(project.id);
    setDeleteStatus("");
    setDeleteStatusIsError(false);
    try {
      const response = await fetch(
        `/api/control/api/v1/projects/${encodeURIComponent(project.id)}/restore`,
        { method: "POST" },
      );
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error?.user_message ?? `恢复失败（${response.status}）`);
      }
      setTrashProjects((current) => current.filter((item) => item.id !== project.id));
      setRemovedProjectIds((current) => {
        const next = new Set(current);
        next.delete(project.id);
        return next;
      });
      setDeleteStatus(`已恢复“${project.name}”。`);
      window.dispatchEvent(new CustomEvent("product-factory:session-changed"));
      router.refresh();
    } catch (error) {
      setDeleteStatusIsError(true);
      setDeleteStatus(error instanceof Error ? error.message : "恢复失败，请稍后重试。");
    } finally {
      setRestoringProjectId(null);
    }
  }

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
              const project = projectItems.find((candidate) => candidate.id === item.projectId);
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
          <h2 id="projects-title">{view === "projects" ? "真实项目" : "回收箱"}</h2>
          <span>{view === "projects" ? `${projectItems.length} 个项目` : `${trashProjects.length} 个已删除项目`}</span>
          <button
            aria-pressed={view === "trash"}
            className="trash-toggle-button"
            disabled={trashLoading}
            onClick={() => void toggleTrash()}
            type="button"
          >{view === "trash" ? "返回项目" : trashLoading ? "加载中" : "回收箱"}</button>
        </header>
        {view === "projects" && projectItems.length ? <div className="project-controls">
          <div aria-label="项目状态筛选" className="project-filters" role="group">
            {filters.map((item) => {
              const count = item.id === "all" ? projectItems.length : counts[item.id];
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
        </div> : null}
        {view === "trash" ? (
          trashLoading ? (
            <div className="empty-state"><strong>正在加载回收箱</strong><p>只读取当前登录用户已删除的项目。</p></div>
          ) : trashProjects.length ? (
            <div className="project-list trash-list" aria-live="polite">
              <div aria-hidden="true" className="project-table-head">
                <span>项目名称</span><span>原阶段</span><span>删除时间</span><span>恢复说明</span><span>操作</span>
              </div>
              {trashProjects.map((project) => (
                <article className="project-row is-deleted" key={project.id}>
                  <div className="project-name-cell">
                    <span aria-hidden="true" className="project-swatch" />
                    <div><strong>{project.name}</strong><small>Context v{project.context_version}</small></div>
                  </div>
                  <span className="stage-label"><b>{Math.max(1, projectStageIndex(project.state) + 1)}</b><span>{projectStageLabel(project.state)}<small>回收箱</small></span></span>
                  <time dateTime={project.deleted_at}>{formatProjectActivity(project.deleted_at)}</time>
                  <span className="project-next-action">恢复后回到删除前阶段</span>
                  <div className="project-actions">
                    <button
                      className="primary-button restore-button"
                      disabled={restoringProjectId === project.id}
                      onClick={() => void restoreProject(project)}
                      type="button"
                    >{restoringProjectId === project.id ? "恢复中" : "恢复项目"}</button>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state"><strong>回收箱为空</strong><p>删除的项目会保留在这里，可随时恢复。</p></div>
          )
        ) : visible.length ? (
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
                  <div className="project-actions">
                    <Link className="primary-link" href={`/projects/${project.id}`}>{category === "waiting" ? "去处理" : "继续项目"}</Link>
                    <button
                      className="danger-button"
                      disabled={deletingProjectId === project.id}
                      onClick={() => void deleteProject(project)}
                      type="button"
                    >{deletingProjectId === project.id ? "删除中" : "删除"}</button>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">
            <strong>{projectItems.length ? "没有匹配的项目" : "还没有项目"}</strong>
            <p>{projectItems.length ? "调整筛选或搜索词。系统不会用示例项目填充结果。" : "在上方说出你想做的产品，Agent 会从真实项目对齐开始。"}</p>
          </div>
        )}
        {deleteStatus ? <p aria-live="polite" className={`project-delete-status${deleteStatusIsError ? " is-error" : ""}`}>{deleteStatus}</p> : null}
        {view === "projects" && filtered.length > pageSize ? (
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
