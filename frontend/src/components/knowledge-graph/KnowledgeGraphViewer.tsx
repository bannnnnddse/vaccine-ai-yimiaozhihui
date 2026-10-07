import { ArrowCounterClockwise, ArrowLeft, ArrowsOut, Crosshair, MagnifyingGlass, Network, X } from "@phosphor-icons/react";
import cytoscape, { type Core, type EventObject } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getGraphMeta, getGraphNodeDetail, getKnowledgeGraph, searchKnowledgeGraph,
  type GraphEdge, type GraphMeta, type GraphNode, type GraphNodeDetail, type GraphResponse,
  type GraphSearchItem, type GraphSource,
} from "../../services/knowledgeGraphService";
import "./KnowledgeGraphViewer.css";

cytoscape.use(fcose);

const CACHE_PREFIX = "vaccine-ai.knowledge-graph.";
const colors: Record<string, string> = {
  Vaccine: "#1685dc", Disease: "#7c5d9f", Pathogen: "#178b8d", Population: "#d79d38",
  AdverseEvent: "#a25f74", ImmuneEntity: "#397b62", Schedule: "#786ab6",
  Guideline: "#566270", EvidenceSource: "#8c8476",
};
const typeLabels: Record<string, string> = { Vaccine: "疫苗", Disease: "疾病", Pathogen: "病原体", Population: "人群", AdverseEvent: "不良事件", ImmuneEntity: "免疫实体", Schedule: "接种程序", Guideline: "指南", EvidenceSource: "证据来源" };

export function KnowledgeGraphViewer({ onClose }: { onClose: () => void }) {
  const containerRef = useRef<HTMLDivElement>(null); const cyRef = useRef<Core | null>(null);
  const dragStartRef = useRef<number | null>(null);
  const [meta, setMeta] = useState<GraphMeta | null>(null); const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [detail, setDetail] = useState<GraphNodeDetail | null>(null); const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [edgeSources, setEdgeSources] = useState<GraphSource[]>([]);
  const [depth, setDepth] = useState<1 | 2>(1); const [showSources, setShowSources] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [hiddenRelations, setHiddenRelations] = useState<Set<string>>(new Set());
  const inspectorOpen = Boolean(detail || selectedEdge);
  const [query, setQuery] = useState(""); const [results, setResults] = useState<GraphSearchItem[]>([]);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(true); const [versionChanged, setVersionChanged] = useState(false);
  const [sheetOffset, setSheetOffset] = useState(0);

  const load = useCallback(async (
    center?: string,
    requestedDepth: 1 | 2 = depth,
    sourceMode = showSources,
  ) => {
    setLoading(true); setError("");
    try {
      let nextMeta = await getGraphMeta();
      if (meta && meta.version !== nextMeta.version) clearGraphCache(meta.version);
      setMeta(nextMeta);
      const cacheKey = `${CACHE_PREFIX}${nextMeta.version}.${center || "overview"}.${requestedDepth}.${sourceMode}`;
      let nextGraph: GraphResponse | null = null;
      try { const cached = sessionStorage.getItem(cacheKey); if (cached) nextGraph = JSON.parse(cached) as GraphResponse; } catch { /* session storage is optional */ }
      if (!nextGraph) nextGraph = await getKnowledgeGraph({ center, depth: requestedDepth, includeSources: sourceMode });
      if (nextGraph.version !== nextMeta.version) {
        nextMeta = await getGraphMeta(); setMeta(nextMeta);
        nextGraph = await getKnowledgeGraph({ center, depth: requestedDepth, includeSources: sourceMode });
        if (nextGraph.version !== nextMeta.version) throw new Error("图谱版本正在切换，请稍后重试。");
      }
      try { sessionStorage.setItem(cacheKey, JSON.stringify(nextGraph)); } catch { /* optional cache */ }
      setGraph(nextGraph); setVersionChanged(false);
    } catch (reason) { setGraph(null); setError(reason instanceof Error ? reason.message : "知识图谱加载失败。"); }
    finally { setLoading(false); }
  }, [depth, showSources, meta?.version]);

  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const check = async () => { if (document.visibilityState !== "visible") return; try { const current = await getGraphMeta(); if (meta && current.version !== meta.version) setVersionChanged(true); } catch { /* retain current explicit state */ } };
    window.addEventListener("focus", check); document.addEventListener("visibilitychange", check);
    return () => { window.removeEventListener("focus", check); document.removeEventListener("visibilitychange", check); };
  }, [meta]);

  useEffect(() => {
    if (!containerRef.current || !graph) return;
    cyRef.current?.destroy();
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cy = cytoscape({
      container: containerRef.current,
      elements: toCytoscapeElements(graph),
      style: [
        { selector: "node", style: { "background-color": "data(color)", shape: "data(shape)", label: "data(label)", color: "#1e2426", "font-size": 11, "text-wrap": "wrap", "text-max-width": 100, "text-valign": "bottom", "text-margin-y": 7, width: "mapData(degree, 0, 15, 24, 58)", height: "mapData(degree, 0, 15, 24, 58)", "border-width": 2, "border-color": "#f8fcff" } },
        { selector: "edge", style: { width: 1.35, "line-color": "#788181", "target-arrow-color": "#788181", "target-arrow-shape": "triangle", "curve-style": "bezier", opacity: 0.62, label: "", "font-size": 9, color: "#3f4747", "text-background-color": "#fffaf0", "text-background-opacity": 0.9, "text-background-padding": 2 } },
        { selector: "edge.visual-only", style: { "line-style": "dashed", "line-dash-pattern": [5, 6], "line-color": "#6a8493", "target-arrow-shape": "none", opacity: 0.42 } },
        { selector: ":selected", style: { "border-color": "#151a1b", "border-width": 4 } },
        { selector: ".focus", style: { opacity: 1, label: "data(label)" } },
        { selector: "edge.focus", style: { opacity: 1, width: 3, "line-color": "#1685dc", "target-arrow-color": "#1685dc", label: "data(label)" } },
        { selector: ".muted", style: { opacity: 0.12 } },
      ],
      layout: { name: "fcose", animate: !reduced, randomize: true, nodeRepulsion: 7500, idealEdgeLength: 92, quality: "default" },
      minZoom: 0.18, maxZoom: 3.2,
    });
    const selectNode = (event: EventObject) => {
      const id = event.target.id(); cy.elements().addClass("muted");
      event.target.closedNeighborhood().removeClass("muted").addClass("focus");
      setSelectedEdge(null); void getGraphNodeDetail(id).then(setDetail).catch((reason) => setError(reason instanceof Error ? reason.message : "实体详情加载失败。"));
    };
    cy.on("tap", "node", selectNode); cy.on("tap", "edge", (event) => { const edge = graph.edges.find((item) => item.id === event.target.id()) || null; setDetail(null); setSelectedEdge(edge); setEdgeSources([]); if (edge) void getGraphNodeDetail(edge.source).then((value) => setEdgeSources(value.sources)).catch(() => setEdgeSources([])); });
    cy.on("tap", (event) => { if (event.target === cy) { cy.elements().removeClass("muted focus"); setDetail(null); setSelectedEdge(null); } });
    cyRef.current = cy;
    return () => { cy.destroy(); cyRef.current = null; };
  }, [graph]);

  useEffect(() => {
    const cy = cyRef.current; if (!cy) return;
    cy.nodes().forEach((node) => node.style("display", hiddenTypes.has(String(node.data("type"))) ? "none" : "element"));
    cy.edges().forEach((edge) => {
      const endpointHidden = hiddenTypes.has(String(edge.source().data("type"))) || hiddenTypes.has(String(edge.target().data("type")));
      edge.style("display", endpointHidden || hiddenRelations.has(String(edge.data("relation"))) ? "none" : "element");
    });
  }, [hiddenTypes, hiddenRelations, graph]);

  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const controller = new AbortController(); const timer = window.setTimeout(() => searchKnowledgeGraph(query.trim(), controller.signal).then((value) => setResults(value.items)).catch(() => setResults([])), 220);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query]);

  const relationList = useMemo(() => detail?.relations.flatMap((group) => group.neighbors.map((node) => ({ ...node, relation: group.relation_label }))) || [], [detail]);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => cyRef.current?.resize());
    return () => window.cancelAnimationFrame(frame);
  }, [inspectorOpen]);
  const openNode = async (node: GraphSearchItem | GraphNode) => { setQuery(node.label); setResults([]); await load(node.id, depth); };
  const relayout = () => cyRef.current?.layout({ name: "fcose", animate: false, randomize: true }).run();
  const returnToOverview = () => {
    setDepth(1); setShowSources(false); setHiddenTypes(new Set()); setHiddenRelations(new Set());
    setQuery(""); setResults([]); setDetail(null); setSelectedEdge(null); setEdgeSources([]);
    void load(undefined, 1, false);
  };

  return <section className="kg-viewer" aria-label="知识图谱观测台">
    <header className="kg-header">
      <button className="kg-icon-button" onClick={onClose} aria-label="返回问答"><ArrowLeft /></button>
      <div className="kg-heading">
        <span>KNOWLEDGE OBSERVATORY / 01</span>
        <div className="kg-title-row">
          <h1>疫苗知识图谱</h1>
          <p>输入想了解的内容，一键展开相关知识网络</p>
        </div>
      </div>
      {meta && <div className="kg-version"><span>当前快照</span><strong>{meta.version.slice(0, 24)}</strong><small>{meta.node_count} 节点 · {meta.edge_count} 关系 · {new Date(meta.updated_at).toLocaleString("zh-CN")}</small></div>}
    </header>
    {versionChanged && <button className="kg-update" onClick={() => void load()}>知识库已有新版本，点击载入最新图谱 ↻</button>}
    <div className={`kg-workspace${inspectorOpen ? " has-inspector" : ""}`}>
      <aside className="kg-tools"><p className="kg-index">01 / FIND</p><label className="kg-search"><MagnifyingGlass /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 HPV 疫苗、宫颈癌…" aria-label="搜索图谱实体" /></label>{results.length > 0 && <div className="kg-results" role="listbox">{results.map((item) => <button key={item.id} role="option" onClick={() => void openNode(item)}><i style={{ background: colors[item.type] }} /><span>{item.label}<small>{item.type}</small></span></button>)}</div>}
        <p className="kg-index">02 / RANGE</p><div className="kg-segment"><button className={depth === 1 ? "is-active" : ""} onClick={() => { setDepth(1); void load(graph?.center_id || undefined, 1); }}>1 层</button><button className={depth === 2 ? "is-active" : ""} onClick={() => { setDepth(2); void load(graph?.center_id || undefined, 2); }}>2 层</button></div><label className="kg-toggle"><input type="checkbox" checked={showSources} onChange={(event) => { const checked = event.target.checked; setShowSources(checked); void load(graph?.center_id || undefined, depth, checked); }} /><span />显示来源节点</label>
        <p className="kg-index">03 / FILTER</p><div className="kg-filter-list">{Object.entries(colors).map(([type, color]) => <label key={type}><input type="checkbox" checked={!hiddenTypes.has(type)} onChange={() => setHiddenTypes(toggleSet(hiddenTypes, type))} /><i style={{ background: color }} />{typeLabels[type] || type}</label>)}</div>{graph && <details className="kg-relation-filter"><summary>关系类型</summary>{Array.from(new Map(graph.edges.map((edge) => [edge.relation, edge.relation_label]))).map(([relation, label]) => <label key={relation}><input type="checkbox" checked={!hiddenRelations.has(relation)} onChange={() => setHiddenRelations(toggleSet(hiddenRelations, relation))} />{label}</label>)}</details>}
      </aside>
      <main className="kg-stage"><div className="kg-canvas" ref={containerRef} aria-label="可缩放与拖拽的知识图谱画布" />{loading && <div className="kg-state"><Network size={42} /><strong>正在读取当前图谱快照</strong><span>不会重新解析文档或调用抽取模型</span></div>}{error && <div className="kg-state kg-state--error"><strong>{error}</strong><button onClick={() => void load()}>重新加载</button></div>}{graph?.truncated && <div className="kg-truncated">当前为精选概览；请搜索实体展开完整邻域。</div>}<div className="kg-controls"><button onClick={() => cyRef.current?.fit(undefined, 38)} aria-label="适配画布" title="适配画布"><ArrowsOut /></button><button onClick={relayout} aria-label="重新布局" title="重新布局"><Network /></button><button onClick={() => { cyRef.current?.elements().removeClass("muted focus"); cyRef.current?.fit(undefined, 38); setDetail(null); setSelectedEdge(null); }} aria-label="清除选择" title="清除选择"><Crosshair /></button><button onClick={returnToOverview} aria-label="返回精选概览" title="返回精选概览"><ArrowCounterClockwise /></button></div></main>
      <aside className={`kg-inspector${inspectorOpen ? " is-open" : ""}`} style={sheetOffset ? { transform: `translateY(${sheetOffset}px)` } : undefined}><div className="kg-sheet-handle" aria-hidden="true" onPointerDown={(event) => { dragStartRef.current = event.clientY; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerMove={(event) => { if (dragStartRef.current !== null) setSheetOffset(Math.max(0, event.clientY - dragStartRef.current)); }} onPointerUp={() => { if (sheetOffset > 110) { setDetail(null); setSelectedEdge(null); } dragStartRef.current = null; setSheetOffset(0); }} /><button className="kg-inspector-close" onClick={() => { setDetail(null); setSelectedEdge(null); }} aria-label="关闭详情"><X /></button><p className="kg-index">04 / EVIDENCE</p>{detail && <><span className="kg-type">{typeLabels[detail.node.type] || detail.node.type}</span><h2>{detail.node.label}</h2><div className="kg-stat"><span>关联度 {detail.node.degree}</span><span>来源 {detail.node.source_count}</span></div><h3>当前关系列表</h3><ul className="kg-relation-list">{relationList.map((item) => <li key={`${item.relation}-${item.id}`}><button onClick={() => void openNode(item)}><span>{item.relation}</span><strong>{item.label}</strong></button></li>)}</ul><h3>来源证据</h3><div className="kg-sources">{detail.sources.map((source, index) => <article key={`${source.chunk_id}-${index}`}><p>“{source.quote}”</p><strong>{source.file_name}{source.page ? ` · 第 ${source.page} 页` : ""}</strong>{source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">查看原文 ↗</a>}<code>{source.chunk_id}</code></article>)}</div></>}{selectedEdge && <><span className="kg-type">DIRECTED RELATION</span><h2>{selectedEdge.relation_label}</h2><p className="kg-edge-route">{nodeLabel(graph, selectedEdge.source)} <b>→</b> {nodeLabel(graph, selectedEdge.target)}</p><div className="kg-stat"><span>置信度 {(selectedEdge.confidence * 100).toFixed(0)}%</span><span>{selectedEdge.source_count} 条证据</span></div><h3>支持来源</h3><div className="kg-sources">{edgeSources.map((source, index) => <article key={`${source.chunk_id}-${index}`}><p>“{source.quote}”</p><strong>{source.file_name}{source.page ? ` · 第 ${source.page} 页` : ""}</strong>{source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">查看原文 ↗</a>}<code>{source.chunk_id}</code></article>)}</div></>}</aside>
    </div>
  </section>;
}

function nodeLabel(graph: GraphResponse | null, id: string) { return graph?.nodes.find((node) => node.id === id)?.label || id; }

function clearGraphCache(version: string) {
  try {
    Object.keys(sessionStorage).filter((key) => key.startsWith(`${CACHE_PREFIX}${version}.`)).forEach((key) => sessionStorage.removeItem(key));
  } catch { /* session storage is optional */ }
}

function toggleSet(current: Set<string>, value: string) {
  const next = new Set(current); if (next.has(value)) next.delete(value); else next.add(value); return next;
}

export function toCytoscapeElements(graph: GraphResponse) {
  return [
    ...graph.nodes.map((node) => ({
      data: {
        ...node,
        color: colors[node.type] || "#52636c",
        // A single circular silhouette makes dense graphs easier to scan; color
        // remains the stable visual encoding for entity type.
        shape: "ellipse",
      },
    })),
    ...graph.edges.map((edge) => ({
      classes: edge.visual_only ? "visual-only" : undefined,
      data: { ...edge, label: edge.relation_label },
    })),
  ];
}

export default KnowledgeGraphViewer;
