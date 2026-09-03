export interface GraphMeta {
  version: string;
  knowledge_base_version: string;
  updated_at: string;
  source_documents: number;
  node_count: number;
  edge_count: number;
  schema_version: string;
  model: string;
}

export interface GraphNode {
  id: string; label: string; type: string; aliases: string[]; degree: number; source_count: number;
}
export interface GraphEdge {
  id: string; source: string; target: string; relation: string; relation_label: string;
  confidence: number; source_count: number; visual_only: boolean;
}
export interface GraphResponse {
  version: string; knowledge_base_version: string; center_id: string | null; depth: number;
  truncated: boolean; nodes: GraphNode[]; edges: GraphEdge[];
}
export interface GraphSearchItem { id: string; label: string; type: string; matched_alias: string | null; }
export interface GraphSource {
  file_name: string; page: number | null; section: string | null; source_type: string;
  source_url: string | null; quote: string; chunk_id: string;
}
export interface GraphNodeDetail {
  version: string; knowledge_base_version: string; node: GraphNode;
  relations: Array<{ relation: string; relation_label: string; neighbors: GraphNode[] }>;
  sources: GraphSource[];
}

export class KnowledgeGraphApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); this.name = "KnowledgeGraphApiError"; }
}

async function api(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`/api/v1/knowledge-graph${path}`, { cache: "no-store", signal });
  if (!response.ok) throw new KnowledgeGraphApiError(response.status === 503 ? "知识图谱正在准备中，请稍后再试。" : `知识图谱请求失败（${response.status}）`, response.status);
  return response.json();
}

export async function getGraphMeta(signal?: AbortSignal): Promise<GraphMeta> {
  const value = await api("/meta", signal);
  if (!isRecord(value) || !strings(value, ["version", "knowledge_base_version", "updated_at", "schema_version", "model"])) throw new KnowledgeGraphApiError("图谱元数据格式无效。", 502);
  return value as unknown as GraphMeta;
}

export async function getKnowledgeGraph(options: {
  center?: string; depth?: 1 | 2; limit?: number; types?: string[]; relations?: string[];
  includeSources?: boolean; signal?: AbortSignal;
} = {}): Promise<GraphResponse> {
  const params = new URLSearchParams({ depth: String(options.depth ?? 1), limit: String(options.limit ?? 250) });
  if (options.center) params.set("center", options.center);
  options.types?.forEach((value) => params.append("types", value));
  options.relations?.forEach((value) => params.append("relations", value));
  if (options.includeSources) params.set("include_sources", "true");
  const value = await api(`?${params}`, options.signal);
  if (!isRecord(value) || !Array.isArray(value.nodes) || !Array.isArray(value.edges) || typeof value.version !== "string") throw new KnowledgeGraphApiError("图谱数据格式无效。", 502);
  return value as unknown as GraphResponse;
}

export async function searchKnowledgeGraph(query: string, signal?: AbortSignal) {
  const value = await api(`/search?q=${encodeURIComponent(query)}&limit=20`, signal);
  if (!isRecord(value) || !Array.isArray(value.items)) throw new KnowledgeGraphApiError("搜索结果格式无效。", 502);
  return value as { version: string; items: GraphSearchItem[] };
}

export async function getGraphNodeDetail(id: string, signal?: AbortSignal): Promise<GraphNodeDetail> {
  const value = await api(`/nodes/${encodeURIComponent(id)}`, signal);
  if (!isRecord(value) || !isRecord(value.node) || !Array.isArray(value.relations) || !Array.isArray(value.sources)) throw new KnowledgeGraphApiError("实体详情格式无效。", 502);
  return value as unknown as GraphNodeDetail;
}

function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null; }
function strings(value: Record<string, unknown>, keys: string[]) { return keys.every((key) => typeof value[key] === "string"); }
