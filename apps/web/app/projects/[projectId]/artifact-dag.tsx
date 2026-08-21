"use client";

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  ReactFlow,
  useNodesState,
} from "@xyflow/react";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";

import type { ApiError, ArtifactContent, ArtifactGraph, ArtifactNode } from "@/lib/contracts";
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

export function ArtifactDag({
  canvasLabel,
  graph,
  referencedArtifactId,
  onPrepareRevision,
  onReferenceArtifact,
}: {
  canvasLabel: string;
  graph: ArtifactGraph;
  referencedArtifactId: string | null;
  onPrepareRevision: (artifact: ArtifactNode) => void;
  onReferenceArtifact: (artifact: ArtifactNode) => void;
}) {
  const [selected, setSelected] = useState<ArtifactNode | null>(null);
  const [preview, setPreview] = useState<ArtifactContent | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [initialViewport] = useState(() => (
    window.innerWidth <= 900
      ? { x: 24, y: 30, zoom: 0.45 }
      : { x: 19, y: -15, zoom: 1 }
  ));
  const graphNodes = useMemo(() => {
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
                <b>v{artifact.latest_version}.0</b>
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
  const edges = useMemo(() => graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source_id,
    target: edge.target_id,
    label: relationLabels[edge.relation] ?? edge.relation,
    labelBgBorderRadius: 4,
    labelBgPadding: [6, 4] as [number, number],
    labelBgStyle: { fill: "#f8f3ee", fillOpacity: 0.98 },
    labelStyle: { fill: "#242321", fontSize: 10, fontWeight: 700 },
    markerEnd: { type: MarkerType.ArrowClosed },
  })), [graph.edges]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    fetch(`/api/control/api/v1/artifacts/${encodeURIComponent(selected.id)}/content`, {
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
      .finally(() => setPreviewLoading(false));
    return () => controller.abort();
  }, [selected]);

  function selectArtifact(artifact: ArtifactNode) {
    setPreview(null);
    setPreviewError("");
    setPreviewLoading(true);
    setSelected(artifact);
  }

  function closePreview() {
    setSelected(null);
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

  return (
    <div className="artifact-workspace">
      {graph.nodes.length ? (
        <ReactFlow
          defaultViewport={initialViewport}
          edges={edges}
          minZoom={0.25}
          nodes={nodes}
          nodesConnectable={false}
          nodesDraggable
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
          <Panel className="canvas-fact-note" position="top-left">
            <strong>{canvasLabel}</strong>
          </Panel>
        </ReactFlow>
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
            <div><dt>版本</dt><dd>v{selected.latest_version}</dd></div>
          </dl>
          <section aria-live="polite" className="artifact-preview-body">
            {previewLoading ? <p>正在读取已校验内容…</p> : null}
            {previewError ? <p className="form-error">{previewError}</p> : null}
            {preview ? <pre>{preview.content}</pre> : null}
          </section>
          <div className="drawer-actions">
            <button className="primary-button" onClick={() => onReferenceArtifact(selected)} type="button">引用到群聊</button>
            <button onClick={() => onPrepareRevision(selected)} type="button">准备修改指令</button>
            <button disabled={!preview} onClick={downloadPreview} type="button">下载当前版本</button>
          </div>
          <p className="drawer-note">内容来自受控 Artifact Root，并在读取时校验路径与 SHA-256；浏览器只做纯文本预览。</p>
        </aside>
      ) : null}
    </div>
  );
}
