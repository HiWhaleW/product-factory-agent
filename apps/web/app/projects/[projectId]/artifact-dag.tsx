"use client";

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  type Node,
  ReactFlow,
  type ReactFlowInstance,
  useNodesState,
} from "@xyflow/react";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { ApiError, ArtifactContent, ArtifactGraph, ArtifactNode, ArtifactVersionIndex } from "@/lib/contracts";
import { projectInternalStageLabel } from "@/lib/stages";

const stageOrder = [
  "alignment", "mrd", "prd", "solution_confirmation", "tech_stack_confirmation",
  "development_backend", "development_frontend", "mvp", "internal_acceptance",
  "seed_beta", "brd", "release_handoff", "feedback",
];

const statusLabels: Record<string, string> = {
  approved: "已批准",
  draft: "草稿",
  failed: "失败",
  running: "生成中",
  superseded: "已有新版",
  waiting_review: "等待评审",
};

const relationLabels: Record<string, string> = {
  blocks: "阻断",
  derived_from: "派生自",
  depends_on: "依赖",
  replaces: "替代",
  reviews: "评审",
};

type ArtifactFlowNode = Node<{
  artifact: ArtifactNode;
  label: ReactNode;
}>;

export function ArtifactDag({
  graph,
  referencedArtifactId,
  onPrepareRevision,
  onReferenceArtifact,
}: {
  graph: ArtifactGraph;
  referencedArtifactId: string | null;
  onPrepareRevision: (artifact: ArtifactNode) => void;
  onReferenceArtifact: (artifact: ArtifactNode) => void;
}) {
  const [selected, setSelected] = useState<ArtifactNode | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [availableVersions, setAvailableVersions] = useState<number[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [preview, setPreview] = useState<ArtifactContent | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [stageFilter, setStageFilter] = useState("all");
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<ArtifactFlowNode> | null>(null);
  const versionRequestId = useRef(0);
  const [initialViewport] = useState(() => (
    window.innerWidth <= 900
      ? { x: 24, y: 30, zoom: 0.45 }
      : { x: 19, y: -15, zoom: 1 }
  ));
  const graphNodes = useMemo<ArtifactFlowNode[]>(() => {
    const stageCounts = new Map<string, number>();
    return graph.nodes.map((artifact) => {
      const row = stageCounts.get(artifact.stage) ?? 0;
      stageCounts.set(artifact.stage, row + 1);
      const column = Math.max(0, stageOrder.indexOf(artifact.stage));
      const stageY = column === 0 ? 276 : column % 2 === 1 ? 110 : 175;
      const stageX = column === 0 ? 90 : column === 1 ? 305 : column * 260 + 45;
      const iconSrc = artifact.stage === "alignment"
        ? "/icon-artifact-brief.png"
        : artifact.stage === "mrd"
          ? "/icon-artifact-mrd.png"
          : "/icon-artifact-prd.png";
      return {
        id: artifact.id,
        position: { x: stageX, y: row * 215 + stageY },
        // React Flow's MiniMap only projects nodes that already have dimensions.
        // Keep these values in sync with `.react-flow__node` so the overview is
        // available on the first render instead of waiting for a measurement pass.
        width: 168,
        height: 190,
        style: { width: 168, height: 190 },
        data: {
          label: (
            <div className="flow-node-content">
              <div className="flow-node-kicker">
                <Image alt="" height={38} src={iconSrc} width={38} />
                <b>v{artifact.latest_version}</b>
              </div>
              <strong>{artifact.title}</strong>
              <span>{statusLabels[artifact.status] ?? artifact.status} · {projectInternalStageLabel(artifact.stage)}</span>
            </div>
          ),
          artifact,
        },
        className: `flow-node status-${artifact.status}${artifact.id === referencedArtifactId ? " is-referenced" : ""}`,
      };
    });
  }, [graph.nodes, referencedArtifactId]);
  const [nodes, setNodes, onNodesChange] = useNodesState(graphNodes);

  useEffect(() => {
    setNodes((currentNodes) => {
      const currentPositions = new Map(
        currentNodes.map((node) => [node.id, node.position]),
      );
      return graphNodes.map((node) => ({
        ...node,
        position: currentPositions.get(node.id) ?? node.position,
      }));
    });
  }, [graphNodes, setNodes]);
  const stageOptions = useMemo(() => stageOrder.filter(
    (stage) => graph.nodes.some((artifact) => artifact.stage === stage),
  ), [graph.nodes]);
  const visibleNodes = useMemo(
    () => stageFilter === "all" ? nodes : nodes.filter((node) => node.data.artifact && (node.data.artifact as ArtifactNode).stage === stageFilter),
    [nodes, stageFilter],
  );
  const renderedNodes = useMemo(
    () => nodes.map((node) => ({
      ...node,
      hidden: stageFilter !== "all" && node.data.artifact.stage !== stageFilter,
    })),
    [nodes, stageFilter],
  );
  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const edges = useMemo(() => graph.edges.filter(
    (edge) => visibleNodeIds.has(edge.source_id) && visibleNodeIds.has(edge.target_id),
  ).map((edge) => ({
    id: edge.id,
    source: edge.source_id,
    target: edge.target_id,
    label: relationLabels[edge.relation] ?? edge.relation,
    labelBgBorderRadius: 4,
    labelBgPadding: [6, 4] as [number, number],
    labelBgStyle: { fill: "#f8f3ee", fillOpacity: 0.98 },
    labelStyle: { fill: "#242321", fontSize: 10, fontWeight: 700 },
    markerEnd: { type: MarkerType.ArrowClosed },
  })), [graph.edges, visibleNodeIds]);

  useEffect(() => {
    if (!selected || selectedVersion === null) return;
    const controller = new AbortController();
    fetch(`/api/control/api/v1/artifacts/${encodeURIComponent(selected.id)}/content?version=${selectedVersion}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        const body = (await response.json()) as ArtifactContent & ApiError;
        if (!response.ok) throw new Error(body.error?.user_message ?? "产物内容读取失败。");
        setPreview(body);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setPreviewError(error instanceof TypeError ? "网络连接失败，产物内容尚未读取。" : error instanceof Error ? error.message : "产物内容读取失败。");
      })
      .finally(() => {
        if (!controller.signal.aborted) setPreviewLoading(false);
      });
    return () => controller.abort();
  }, [selected, selectedVersion]);

  async function loadAvailableVersions(artifact: ArtifactNode, requestId: number) {
    let versions: ArtifactVersionIndex[] = [];
    try {
      const response = await fetch(
        `/api/control/api/v1/artifacts/${encodeURIComponent(artifact.id)}/versions`,
        { cache: "no-store" },
      );
      if (response.ok) versions = (await response.json()) as ArtifactVersionIndex[];
    } catch {
      // Keep the known latest version when the index endpoint is temporarily unavailable.
    }
    if (requestId !== versionRequestId.current) return;
    const persistedVersions = versions
      .filter((version) => version.content_available)
      .map((version) => version.version);
    setAvailableVersions(persistedVersions.length ? persistedVersions : [artifact.latest_version]);
    setVersionsLoading(false);
  }

  function selectArtifact(artifact: ArtifactNode) {
    const requestId = ++versionRequestId.current;
    setPreview(null);
    setPreviewError("");
    setPreviewLoading(true);
    setAvailableVersions([artifact.latest_version]);
    setVersionsLoading(true);
    setSelected(artifact);
    setSelectedVersion(artifact.latest_version);
    void loadAvailableVersions(artifact, requestId);
  }

  function closePreview() {
    versionRequestId.current += 1;
    setSelected(null);
    setSelectedVersion(null);
    setAvailableVersions([]);
    setVersionsLoading(false);
    setPreview(null);
    setPreviewError("");
    setPreviewLoading(false);
  }

  function downloadPreview() {
    if (!preview) return;
    const blob = new Blob([preview.content], { type: `${preview.content_type};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = preview.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function selectedArtifactVersion() {
    if (!selected || selectedVersion === null) return null;
    return { ...selected, latest_version: selectedVersion };
  }

  function fitVisibleNodes() {
    if (!flowInstance || !visibleNodes.length) return;
    void flowInstance.fitView({ maxZoom: 1, nodes: visibleNodes, padding: 0.18 });
  }

  function changeStageFilter(nextStage: string) {
    setStageFilter(nextStage);
    if (selected && nextStage !== "all" && selected.stage !== nextStage) closePreview();
  }

  return (
    <div className="artifact-workspace">
      {graph.nodes.length ? (
        <>
          <div aria-label="产物画布工具" className="artifact-toolbar" role="group">
            <label htmlFor="artifact-stage-filter">阶段</label>
            <select
              id="artifact-stage-filter"
              onChange={(event) => changeStageFilter(event.target.value)}
              value={stageFilter}
            >
              <option value="all">全部阶段（{graph.nodes.length}）</option>
              {stageOptions.map((stage) => (
                <option key={stage} value={stage}>
                  {projectInternalStageLabel(stage)}（{graph.nodes.filter((artifact) => artifact.stage === stage).length}）
                </option>
              ))}
            </select>
            <button disabled={!visibleNodes.length} onClick={fitVisibleNodes} type="button">定位产物</button>
          </div>
          <ReactFlow
            defaultViewport={initialViewport}
            edges={edges}
            minZoom={0.25}
            nodes={renderedNodes}
            nodesConnectable={false}
            nodesDraggable
            onInit={setFlowInstance}
            onNodesChange={onNodesChange}
            onNodeClick={(_, node) => selectArtifact(node.data.artifact as ArtifactNode)}
            onPaneClick={closePreview}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} size={1} />
            <Controls showInteractive={false} />
            <MiniMap
              ariaLabel="产物画布小地图"
              maskColor="rgb(36 35 33 / 8%)"
              nodeColor="#ffd71f"
              nodeStrokeColor="#242321"
              nodeStrokeWidth={3}
              pannable
              style={{ height: 112, width: 180 }}
              zoomable
            />
          </ReactFlow>
        </>
      ) : (
        <div className="dag-empty">
          <div aria-hidden="true" className="empty-node">01</div>
          <strong>还没有持久化产物</strong>
          <p>真实 Artifact 出现后会在这里形成累计依赖图；消息或构建成功不会被冒充为产物。</p>
        </div>
      )}
      {selected ? (
        <aside aria-label="产物预览" className="preview-drawer">
          <button aria-label="关闭产物预览" className="drawer-close" onClick={closePreview} type="button">×</button>
          <p className="eyebrow">ARTIFACT PREVIEW</p>
          <h3>{selected.title}</h3>
          <dl>
            <div><dt>类型</dt><dd>{selected.kind}</dd></div>
            <div><dt>阶段</dt><dd>{selected.stage}</dd></div>
            <div><dt>状态</dt><dd>{statusLabels[selected.status] ?? selected.status}</dd></div>
            <div>
              <dt>版本</dt>
              <dd>
                {versionsLoading ? <span>正在核对修订记录…</span> : null}
                {!versionsLoading && availableVersions.length > 1 ? (
                  <select
                    aria-label="选择产物修订版"
                    onChange={(event) => {
                      setPreview(null);
                      setPreviewError("");
                      setPreviewLoading(true);
                      setSelectedVersion(Number(event.target.value));
                    }}
                    value={selectedVersion ?? selected.latest_version}
                  >
                    {availableVersions.map((version) => (
                      <option key={version} value={version}>v{version}{version === selected.latest_version ? " · 最新" : " · 历史"}</option>
                    ))}
                  </select>
                ) : null}
                {!versionsLoading && availableVersions.length === 1 ? <span>v{availableVersions[0]} · 当前持久化版本</span> : null}
              </dd>
            </div>
          </dl>
          <section aria-live="polite" className="artifact-preview-body">
            {previewLoading ? <p>正在读取已校验内容…</p> : null}
            {previewError ? <p className="form-error">{previewError}</p> : null}
            {preview ? <pre>{preview.content}</pre> : null}
          </section>
          <div className="drawer-actions">
            <button className="primary-button" onClick={() => {
              const artifact = selectedArtifactVersion();
              if (artifact) onReferenceArtifact(artifact);
            }} type="button">引用 v{selectedVersion} 到群聊</button>
            <button onClick={() => {
              const artifact = selectedArtifactVersion();
              if (artifact) onPrepareRevision(artifact);
            }} type="button">基于 v{selectedVersion} 修改</button>
            <button disabled={!preview} onClick={downloadPreview} type="button">下载 v{selectedVersion}</button>
          </div>
        </aside>
      ) : null}
    </div>
  );
}
