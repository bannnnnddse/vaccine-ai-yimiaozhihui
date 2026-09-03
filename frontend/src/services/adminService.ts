export type GapStatus = "pending" | "in_review" | "hold" | "approved" | "publishing" | "rejected" | "published";

export interface GraphJob {
  task_id: string; status: "queued" | "running" | "completed" | "failed"; kind: string;
  stage: string; progress: number; processed_chunks: number; total_chunks: number;
  result_graph_version: string | null; result_index_version: string | null; error: string | null;
}

export interface CandidateClaim { text: string; evidence_pmids: string[]; }
export interface InternalEvidence {
  file_name: string; page: number | null; source_type: string | null; source_url: string | null;
  similarity: number; excerpt: string; relative_path?: string | null; source_title?: string | null;
  section?: string | null;
}
export interface PubMedEvidence {
  pmid: string; title: string; abstract_excerpt: string; journal: string; year: number | null;
  doi: string | null; url: string;
}
export interface KnowledgeGap {
  id: string; original_query: string; rewritten_query: string; internal_evidence: InternalEvidence[];
  assessment_status: "partial" | "insufficient" | "conflict"; assessment_reason: string;
  missing_aspects: string[]; pubmed_pmids: string[]; pubmed_evidence: PubMedEvidence[];
  candidate_claims: CandidateClaim[]; trigger_reason: string; status: GapStatus;
  reviewer_note: string | null; created_at: string; reviewed_at: string | null;
  approved_at: string | null; published_at: string | null; version: number;
  draft_file_name: string | null; draft_sha256: string | null; draft_generated_at: string | null;
  published_relative_path: string | null;
}
export interface AuditEvent {
  id: number; gap_id: string; event_type: string; actor: string;
  details: Record<string, unknown>; created_at: string;
}
export interface GapDetail { gap: KnowledgeGap; audit_events: AuditEvent[]; }
export interface DraftPreview { content: string; sha256: string; generated_at: string; }

let csrfToken = "";

export class AdminApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); this.name = "AdminApiError"; }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body) headers.set("Content-Type", "application/json");
  if (init?.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`/api/v1/admin${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `管理服务请求失败（HTTP ${response.status}）`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch { /* Preserve the stable fallback. */ }
    throw new AdminApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function loginAdmin(username: string, password: string) {
  const session = await request<{ username: string; csrf_token: string; expires_at: number }>("/session", {
    method: "POST", body: JSON.stringify({ username, password }),
  });
  csrfToken = session.csrf_token;
  return session;
}

export async function restoreAdminSession() {
  const session = await request<{ username: string; csrf_token: string; expires_at: number }>("/session");
  csrfToken = session.csrf_token;
  return session;
}

export async function logoutAdmin() {
  await request<void>("/session", { method: "DELETE" });
  csrfToken = "";
}

export async function listKnowledgeGaps(status: GapStatus | "", query = "") {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (query.trim()) params.set("query", query.trim());
  return request<{ items: KnowledgeGap[]; total: number }>(`/knowledge-gaps?${params}`);
}

export const getKnowledgeGap = (id: string) => request<GapDetail>(`/knowledge-gaps/${encodeURIComponent(id)}`);

export async function saveKnowledgeGapReview(id: string, version: number, reviewerNote: string, claims: CandidateClaim[]) {
  return request<GapDetail>(`/knowledge-gaps/${encodeURIComponent(id)}/review`, {
    method: "PUT", body: JSON.stringify({ version, reviewer_note: reviewerNote, candidate_claims: claims }),
  });
}

export async function holdKnowledgeGap(id: string, version: number, reviewerNote: string) {
  return request<GapDetail>(`/knowledge-gaps/${encodeURIComponent(id)}/hold`, {
    method: "POST", body: JSON.stringify({ version, reviewer_note: reviewerNote }),
  });
}

export async function rejectKnowledgeGap(id: string, version: number, reviewerNote: string) {
  return request<GapDetail>(`/knowledge-gaps/${encodeURIComponent(id)}/reject`, {
    method: "POST", body: JSON.stringify({ version, reviewer_note: reviewerNote }),
  });
}

export async function approveKnowledgeGap(
  id: string, version: number, title: string, reviewerNote: string, claims: CandidateClaim[],
) {
  return request<GapDetail>(`/knowledge-gaps/${encodeURIComponent(id)}/approve`, {
    method: "POST",
    body: JSON.stringify({ version, title, reviewer_note: reviewerNote, candidate_claims: claims }),
  });
}

export const getKnowledgeDraft = (id: string) => request<DraftPreview>(`/knowledge-gaps/${encodeURIComponent(id)}/draft`);

export async function publishKnowledgeGap(id: string, version: number) {
  return request<GraphJob>(`/knowledge-gaps/${encodeURIComponent(id)}/publish`, {
    method: "POST", body: JSON.stringify({ version }),
  });
}

export async function rebuildKnowledgeGraph(mode: "incremental" | "full", forceReextract = false) {
  return request<GraphJob>("/knowledge-graph/rebuild", {
    method: "POST", body: JSON.stringify({ mode, force_reextract: forceReextract }),
  });
}

export const getGraphJob = (id: string) => request<GraphJob>(`/knowledge-graph/jobs/${encodeURIComponent(id)}`);

export async function getPublicGraphMeta() {
  const response = await fetch("/api/v1/knowledge-graph/meta", { cache: "no-store" });
  if (!response.ok) throw new AdminApiError("当前还没有可用的知识图谱快照。", response.status);
  return response.json() as Promise<{ version: string; updated_at: string; node_count: number; edge_count: number; knowledge_base_version: string }>;
}

export const draftDownloadUrl = (id: string) => `/api/v1/admin/knowledge-gaps/${encodeURIComponent(id)}/draft/download`;
