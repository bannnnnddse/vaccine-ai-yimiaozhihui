export interface GenerationRequest {
  topic: string;
  audience?: string;
  outputType?: "academic" | "poster" | "interactive" | "video";
}

interface ChatApiResponse {
  answer: unknown;
  is_vaccine_related: unknown;
  session_id: unknown;
  sources: unknown;
}

interface ChatSourceApiResponse {
  file_name: unknown;
  page: unknown;
  content: unknown;
  source_type?: unknown;
  source_title?: unknown;
  source_url?: unknown;
  section?: unknown;
  pages?: unknown;
  title?: unknown;
  pmid?: unknown;
  journal?: unknown;
  year?: unknown;
  doi?: unknown;
  url?: unknown;
  snippet?: unknown;
}

export interface KnowledgeSource {
  fileName: string;
  page: number | null;
  content: string;
  sourceType?: "pdf" | "web" | "pubmed" | "curated";
  sourceTitle?: string;
  sourceUrl?: string;
  section?: string;
  pages?: number[];
  pmid?: string;
  journal?: string;
  year?: number;
  doi?: string;
}

export interface ChatAnswerRequest {
  question: string;
  presetAnswer?: string;
  sessionId?: string | null;
  history?: ChatHistoryItem[];
  signal?: AbortSignal;
}

export interface ChatHistoryItem {
  role: "user" | "assistant";
  content: string;
}

export interface ChatAnswerResult {
  answer: string;
  isVaccineRelated: boolean;
  sessionId: string | null;
  sources: KnowledgeSource[];
}

export type ChatProgressHandler = (message: string) => void;

export type ImageJobStage =
  | "queued"
  | "rewriting_prompt"
  | "generating"
  | "critic_review_1"
  | "auto_revising"
  | "guard_check"
  | "critic_review_2"
  | "awaiting_human_feedback"
  | "editing_with_bbox"
  | "critic_review_final"
  | "completed"
  | "failed"
  | "cancelled";

export type NormalizedBBox = [number, number, number, number];
export type RevisionOrigin = "initial" | "auto" | "human";
export type ImageProcessStage = "understanding" | "prompt_rewrite" | "generation" | "visual_critic" | "auto_revision" | "edit_rewrite" | "scope_guard" | "human_feedback" | "final_critic" | "completed" | "warning";
export interface ImageProcessEvent {
  id: string;
  stage: ImageProcessStage;
  title: string;
  detail?: string;
  status: "running" | "completed" | "warning";
  createdAt: string;
}

export async function generateConversationTitle(messages: ChatHistoryItem[]): Promise<string> {
  const compactMessages = messages
    .filter((message) => message.content.trim())
    .slice(0, 8)
    .map((message) => ({ role: message.role, content: message.content.trim().slice(0, 4_000) }));
  const response = await fetch("/api/v1/conversations/title", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: compactMessages }),
  });
  if (!response.ok) throw new Error(`Conversation title request failed (HTTP ${response.status})`);
  const data: unknown = await response.json();
  if (!data || typeof data !== "object" || typeof (data as { title?: unknown }).title !== "string") {
    throw new Error("Conversation title service returned an invalid response");
  }
  const title = (data as { title: string }).title.trim();
  if (!title || title.length > 60 || /[\r\n]/.test(title)) {
    throw new Error("Conversation title service returned an invalid title");
  }
  return title;
}

export interface VisualIssue {
  issueType: "text_error" | "text_regeneration" | "layout" | "artifact" | "anatomy" | "style_inconsistency" | "ip_identity_mismatch" | "scientific_expression" | "other";
  severity: "low" | "medium" | "high";
  description: string;
  bbox: NormalizedBBox | null;
  confidence: number;
  suggestedFix: string;
  observedText?: string;
  replacementText?: string;
  autoFixable: boolean;
  humanInputRequired: boolean;
}

export interface VisualCriticResult {
  overallStatus: "pass" | "needs_revision" | "needs_human_review" | "fail";
  summary: string;
  recommendedAction: "accept" | "auto_fix" | "request_human_feedback" | "reject";
  autoFixable: boolean;
  humanInputRequired: boolean;
  issues: VisualIssue[];
}

export interface EditScopeGuardResult {
  passed: boolean;
  outsideChangeScore: number;
  threshold: number;
  changedOutsideBBox: boolean;
  insideChangeScore: number;
  minimumInsideChange: number;
  insufficientChangeInsideBBox: boolean;
  outsideChangeRegions: NormalizedBBox[];
  notes: string;
}

export interface ImageJob {
  jobId: string;
  stage: ImageJobStage;
  imageUrl?: string;
  imageId?: string;
  candidateImageUrl?: string;
  previousImageUrl?: string;
  previousImageId?: string;
  error?: string | null;
  retryable?: boolean;
  criticResult?: VisualCriticResult;
  guardResult?: EditScopeGuardResult;
  autoRevisionCount: number;
  revisionOrigin?: RevisionOrigin;
  previousRevisionOrigin?: RevisionOrigin;
  traceId: string;
  traceEvents: ImageProcessEvent[];
}

interface ImageJobApiResponse {
  job_id: unknown;
  stage: unknown;
  image_url?: unknown;
  image_id?: unknown;
  candidate_image_url?: unknown;
  previous_image_url?: unknown;
  previous_image_id?: unknown;
  error?: unknown;
  retryable?: unknown;
  critic_result?: unknown;
  guard_result?: unknown;
  auto_revision_count?: unknown;
  revision_origin?: unknown;
  previous_revision_origin?: unknown;
  trace_id?: unknown;
  trace_events?: unknown;
}

const imageJobStages: readonly ImageJobStage[] = [
  "queued",
  "rewriting_prompt",
  "generating",
  "critic_review_1",
  "auto_revising",
  "guard_check",
  "critic_review_2",
  "awaiting_human_feedback",
  "editing_with_bbox",
  "critic_review_final",
  "completed",
  "failed",
  "cancelled",
];

export class ImageJobRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ImageJobRequestError";
  }
}

export class ChatRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: string,
  ) {
    super(message);
    this.name = "ChatRequestError";
  }
}

const delay = (milliseconds: number) => new Promise<void>((resolve) => globalThis.setTimeout(resolve, milliseconds));

export async function generateChatAnswer(
  { question, presetAnswer, sessionId, history = [] }: ChatAnswerRequest,
): Promise<ChatAnswerResult> {
  if (presetAnswer) {
    await delay(2_000);
    return { answer: presetAnswer, isVaccineRelated: true, sessionId: null, sources: [] };
  }

  const recentHistory = history
    .filter((item) => item.content.trim())
    .slice(-8)
    .map((item) => ({ role: item.role, content: item.content.trim() }));
  const requestBody: { question: string; session_id?: string; history?: ChatHistoryItem[] } = { question };
  if (sessionId?.trim()) requestBody.session_id = sessionId;
  if (recentHistory.length > 0) requestBody.history = recentHistory;

  let response = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok && response.status === 409 && sessionId?.trim()) {
    response = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        ...(recentHistory.length > 0 ? { history: recentHistory } : {}),
      }),
    });
  }

  if (!response.ok) {
    throw new ChatRequestError(
      `AI service request failed (HTTP ${response.status})`,
      response.status,
      await readChatErrorDetail(response),
    );
  }

  const data = await response.json() as ChatApiResponse;
  if (typeof data.answer !== "string" || !data.answer.trim()) {
    throw new Error("AI service returned an empty answer");
  }
  if (typeof data.is_vaccine_related !== "boolean") {
    throw new Error("AI service returned an invalid vaccine-related flag");
  }
  if (typeof data.session_id !== "string" || !data.session_id.trim()) {
    throw new Error("AI service returned an invalid session ID");
  }

  return {
    answer: data.answer,
    isVaccineRelated: data.is_vaccine_related,
    sessionId: data.session_id,
    sources: parseKnowledgeSources(data.sources),
  };
}

export async function generateChatAnswerStream(
  { question, presetAnswer, sessionId, history = [], signal }: ChatAnswerRequest,
  onProgress: ChatProgressHandler,
): Promise<ChatAnswerResult> {
  if (presetAnswer) {
    await delay(2_000);
    return { answer: presetAnswer, isVaccineRelated: true, sessionId: null, sources: [] };
  }

  const recentHistory = history
    .filter((item) => item.content.trim())
    .slice(-8)
    .map((item) => ({ role: item.role, content: item.content.trim() }));
  const requestBody: { question: string; session_id?: string; history?: ChatHistoryItem[] } = { question };
  if (sessionId?.trim()) requestBody.session_id = sessionId;
  if (recentHistory.length > 0) requestBody.history = recentHistory;

  let response = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(requestBody),
    signal,
  });
  if (!response.ok && response.status === 409 && sessionId?.trim()) {
    response = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, ...(recentHistory.length > 0 ? { history: recentHistory } : {}) }),
      signal,
    });
  }
  if (!response.ok) {
    throw new ChatRequestError(`AI service request failed (HTTP ${response.status})`, response.status);
  }
  return readChatStream(response, onProgress);
}

async function readChatErrorDetail(response: Response): Promise<string | undefined> {
  try {
    const data = await response.json() as { detail?: unknown };
    if (typeof data.detail === "string" && data.detail.trim()) return data.detail.trim();
  } catch {
    // Non-JSON error bodies still surface the HTTP status.
  }
  return undefined;
}

async function readChatStream(
  response: Response,
  onProgress: ChatProgressHandler,
): Promise<ChatAnswerResult> {
  if (!response.body) throw new Error("AI service did not return a response stream");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
        const event = /^event:\s*(.+)$/m.exec(frame)?.[1]?.trim();
        const dataText = /^data:\s*(.+)$/m.exec(frame)?.[1];
        if (!event || !dataText) continue;
        let data: unknown;
        try {
          data = JSON.parse(dataText);
        } catch {
          throw new Error("AI service returned an invalid progress event");
        }
        if (event === "stage") {
          const message = typeof (data as { message?: unknown }).message === "string"
            ? (data as { message: string }).message.trim()
            : "";
          if (message) onProgress(message);
          continue;
        }
        if (event === "error") {
          const status = (data as { status?: unknown }).status;
          const detail = (data as { detail?: unknown }).detail;
          throw new ChatRequestError(
            "AI service request failed",
            typeof status === "number" && Number.isInteger(status) ? status : 500,
            typeof detail === "string" && detail.trim() ? detail.trim() : undefined,
          );
        }
        if (event === "final") return parseChatAnswer(data);
      }
      if (done) break;
    }
  } finally {
    reader.releaseLock();
  }
  throw new Error("AI service ended before returning an answer");
}

function parseChatAnswer(data: unknown): ChatAnswerResult {
  const value = data as ChatApiResponse;
  if (typeof value.answer !== "string" || !value.answer.trim()) {
    throw new Error("AI service returned an empty answer");
  }
  if (typeof value.is_vaccine_related !== "boolean") {
    throw new Error("AI service returned an invalid vaccine-related flag");
  }
  if (typeof value.session_id !== "string" || !value.session_id.trim()) {
    throw new Error("AI service returned an invalid session ID");
  }
  return {
    answer: value.answer,
    isVaccineRelated: value.is_vaccine_related,
    sessionId: value.session_id,
    sources: parseKnowledgeSources(value.sources),
  };
}

function parseKnowledgeSources(value: unknown): KnowledgeSource[] {
  if (!Array.isArray(value)) {
    throw new Error("AI service returned an invalid source list");
  }
  return value.map((item) => {
    const source = item as ChatSourceApiResponse;
    const sourceType = source.source_type === undefined ? "pdf" : source.source_type;
    const isPdf = sourceType === "pdf";
    const isWeb = sourceType === "web";
    const isPubMed = sourceType === "pubmed";
    const isCurated = sourceType === "curated";
    const hasValidPage = typeof source.page === "number" && Number.isInteger(source.page) && source.page >= 1;
    const hasValidPages = source.pages === undefined || (
      Array.isArray(source.pages)
      && source.pages.length >= 2
      && source.pages.every((page) => typeof page === "number" && Number.isInteger(page) && page >= 1)
    );
    const hasNoPage = source.page === null || source.page === undefined;
    const hasValidWebUrl = typeof source.source_url === "string" && isHttpUrl(source.source_url);
    const hasValidPubMedFields = (
      typeof source.title === "string" && Boolean(source.title.trim())
      && typeof source.pmid === "string" && /^[0-9]{1,10}$/.test(source.pmid)
      && typeof source.url === "string" && isHttpUrl(source.url)
      && typeof source.snippet === "string" && Boolean(source.snippet.trim())
    );
    if (
      typeof source.file_name !== "string" || !source.file_name.trim()
      || typeof source.content !== "string" || !source.content.trim()
      || (!isPdf && !isWeb && !isPubMed && !isCurated)
      || (isPdf && !hasValidPage)
      || ((isWeb || isCurated) && (!hasNoPage || !hasValidWebUrl))
      || (isPubMed && (!hasNoPage || !hasValidPubMedFields))
      || !hasValidPages
      || (source.source_title !== undefined && typeof source.source_title !== "string")
      || (source.section !== undefined && typeof source.section !== "string")
      || (source.journal !== undefined && typeof source.journal !== "string")
      || (source.year !== undefined && (!Number.isInteger(source.year) || (source.year as number) < 1800))
      || (source.doi !== undefined && typeof source.doi !== "string")
    ) {
      throw new Error("AI service returned an invalid source");
    }
    const result: KnowledgeSource = {
      fileName: source.file_name,
      page: isPdf ? source.page as number : null,
      content: source.content,
    };
    if (source.source_type !== undefined || isWeb || isPubMed) result.sourceType = sourceType;
    if (typeof source.source_title === "string" && source.source_title.trim()) {
      result.sourceTitle = source.source_title;
    }
    if (isWeb || isCurated) result.sourceUrl = source.source_url as string;
    if (isPubMed) {
      result.sourceTitle = source.title as string;
      result.sourceUrl = source.url as string;
      result.pmid = source.pmid as string;
      if (typeof source.journal === "string" && source.journal.trim()) result.journal = source.journal;
      if (typeof source.year === "number") result.year = source.year;
      if (typeof source.doi === "string" && source.doi.trim()) result.doi = source.doi;
    }
    if (typeof source.section === "string" && source.section.trim()) result.section = source.section;
    if (Array.isArray(source.pages)) result.pages = [...new Set(source.pages as number[])].sort((a, b) => a - b);
    return result;
  });
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

async function parseImageJobResponse(response: Response): Promise<ImageJob> {
  if (!response.ok) {
    throw new ImageJobRequestError(
      await getImageJobErrorMessage(response),
      response.status,
    );
  }

  let data: ImageJobApiResponse;
  try {
    data = await response.json() as ImageJobApiResponse;
  } catch {
    throw new Error("Image job service returned an invalid JSON response");
  }

  return toImageJob(data);
}

async function getImageJobErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json() as { detail?: unknown };
    if (typeof data.detail === "string" && data.detail.trim()) {
      return data.detail;
    }
  } catch {
    // The HTTP status remains available even when the error body is not JSON.
  }

  return `Image job request failed (HTTP ${response.status})`;
}

function toImageJob(data: ImageJobApiResponse): ImageJob {
  if (typeof data.job_id !== "string" || !data.job_id.trim()) {
    throw new Error("Image job service returned an invalid job ID");
  }
  if (!isImageJobStage(data.stage)) {
    throw new Error("Image job service returned an invalid stage");
  }
  if (data.error !== undefined && data.error !== null && typeof data.error !== "string") {
    throw new Error("Image job service returned an invalid error message");
  }
  if (data.retryable !== undefined && typeof data.retryable !== "boolean") {
    throw new Error("Image job service returned an invalid retryable flag");
  }

  const job: ImageJob = {
    jobId: data.job_id,
    stage: data.stage,
    autoRevisionCount: typeof data.auto_revision_count === "number" ? data.auto_revision_count : 0,
    traceId: typeof data.trace_id === "string" ? data.trace_id : "",
    traceEvents: parseTraceEvents(data.trace_events),
  };

  if (data.error !== undefined) job.error = data.error;
  if (data.retryable !== undefined) job.retryable = data.retryable;

  if (data.image_url !== undefined && data.image_url !== null) {
    if (typeof data.image_url !== "string" || !isGeneratedImageUrl(data.image_url)) {
      throw new Error("Image job service returned an invalid generated image URL");
    }
    job.imageUrl = data.image_url;
  }
  if (data.image_id !== undefined && data.image_id !== null) {
    if (typeof data.image_id !== "string" || !data.image_id.trim()) throw new Error("Image job service returned an invalid image ID");
    job.imageId = data.image_id;
  }
  if (data.candidate_image_url !== undefined && data.candidate_image_url !== null) {
    if (typeof data.candidate_image_url !== "string" || !isGeneratedImageUrl(data.candidate_image_url)) {
      throw new Error("Image job service returned an invalid candidate image URL");
    }
    job.candidateImageUrl = data.candidate_image_url;
  }
  if (data.previous_image_url !== undefined && data.previous_image_url !== null) {
    if (typeof data.previous_image_url !== "string" || !isGeneratedImageUrl(data.previous_image_url)) {
      throw new Error("Image job service returned an invalid previous image URL");
    }
    job.previousImageUrl = data.previous_image_url;
  }
  if (data.previous_image_id !== undefined && data.previous_image_id !== null) {
    if (typeof data.previous_image_id !== "string" || !data.previous_image_id.trim()) {
      throw new Error("Image job service returned an invalid previous image ID");
    }
    job.previousImageId = data.previous_image_id;
  }
  if (data.critic_result !== undefined && data.critic_result !== null) job.criticResult = parseCritic(data.critic_result);
  if (data.guard_result !== undefined && data.guard_result !== null) job.guardResult = parseGuard(data.guard_result);
  if (data.revision_origin !== undefined && data.revision_origin !== null) {
    if (!(["initial", "auto", "human"] as unknown[]).includes(data.revision_origin)) throw new Error("Image job service returned an invalid revision origin");
    job.revisionOrigin = data.revision_origin as RevisionOrigin;
  }
  if (data.previous_revision_origin !== undefined && data.previous_revision_origin !== null) {
    if (!( ["initial", "auto", "human"] as unknown[]).includes(data.previous_revision_origin)) {
      throw new Error("Image job service returned an invalid previous revision origin");
    }
    job.previousRevisionOrigin = data.previous_revision_origin as RevisionOrigin;
  }
  if (!Number.isInteger(job.autoRevisionCount) || job.autoRevisionCount < 0) throw new Error("Image job service returned an invalid revision count");

  return job;
}

function parseTraceEvents(value: unknown): ImageProcessEvent[] {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new Error("Image job service returned an invalid process trace");
  const stages: ImageProcessStage[] = ["understanding", "prompt_rewrite", "generation", "visual_critic", "auto_revision", "edit_rewrite", "scope_guard", "human_feedback", "final_critic", "completed", "warning"];
  return value.map((raw) => {
    const event = raw as Record<string, unknown>;
    if (!event || typeof event !== "object" || typeof event.id !== "string" || !event.id.trim()
      || typeof event.title !== "string" || !event.title.trim()
      || (event.detail !== undefined && event.detail !== null && typeof event.detail !== "string")
      || !stages.includes(event.stage as ImageProcessStage)
      || !["running", "completed", "warning"].includes(String(event.status))
      || typeof event.created_at !== "string" || Number.isNaN(Date.parse(event.created_at))) {
      throw new Error("Image job service returned an invalid process event");
    }
    return {
      id: event.id,
      stage: event.stage as ImageProcessStage,
      title: event.title,
      ...(typeof event.detail === "string" && event.detail ? { detail: event.detail } : {}),
      status: event.status as ImageProcessEvent["status"],
      createdAt: event.created_at,
    };
  });
}

function parseBBox(value: unknown): NormalizedBBox | null {
  if (value === null) return null;
  if (!Array.isArray(value) || value.length !== 4 || value.some((item) => typeof item !== "number" || item < 0 || item > 1)) {
    throw new Error("Image job service returned an invalid bbox");
  }
  const bbox = value as NormalizedBBox;
  if (bbox[2] <= bbox[0] || bbox[3] <= bbox[1]) throw new Error("Image job service returned an invalid bbox");
  return bbox;
}

function parseCritic(value: unknown): VisualCriticResult {
  const item = value as Record<string, unknown>;
  if (!item || typeof item !== "object" || !Array.isArray(item.issues)
    || typeof item.summary !== "string" || typeof item.auto_fixable !== "boolean" || typeof item.human_input_required !== "boolean"
    || !["pass", "needs_revision", "needs_human_review", "fail"].includes(String(item.overall_status))
    || !["accept", "auto_fix", "request_human_feedback", "reject"].includes(String(item.recommended_action))) {
    throw new Error("Image job service returned an invalid critic result");
  }
  const issues = item.issues.map((raw) => {
    const issue = raw as Record<string, unknown>;
    if (!issue || typeof issue.description !== "string" || typeof issue.suggested_fix !== "string"
      || typeof issue.confidence !== "number" || issue.confidence < 0 || issue.confidence > 1
      || typeof issue.auto_fixable !== "boolean" || typeof issue.human_input_required !== "boolean"
      || !["text_error", "text_regeneration", "layout", "artifact", "anatomy", "style_inconsistency", "ip_identity_mismatch", "scientific_expression", "other"].includes(String(issue.issue_type))
      || !["low", "medium", "high"].includes(String(issue.severity))) throw new Error("Image job service returned an invalid critic issue");
    return {
      issueType: issue.issue_type as VisualIssue["issueType"], severity: issue.severity as VisualIssue["severity"],
      description: issue.description, bbox: parseBBox(issue.bbox), confidence: issue.confidence,
      suggestedFix: issue.suggested_fix,
      ...(typeof issue.observed_text === "string" ? { observedText: issue.observed_text } : {}),
      ...(typeof issue.replacement_text === "string" ? { replacementText: issue.replacement_text } : {}),
      autoFixable: issue.auto_fixable, humanInputRequired: issue.human_input_required,
    };
  });
  return {
    overallStatus: item.overall_status as VisualCriticResult["overallStatus"], summary: item.summary,
    recommendedAction: item.recommended_action as VisualCriticResult["recommendedAction"],
    autoFixable: item.auto_fixable, humanInputRequired: item.human_input_required, issues,
  };
}

function parseGuard(value: unknown): EditScopeGuardResult {
  const item = value as Record<string, unknown>;
  if (!item || typeof item !== "object" || typeof item.passed !== "boolean"
    || typeof item.outside_change_score !== "number" || typeof item.threshold !== "number"
    || typeof item.changed_outside_bbox !== "boolean"
    || typeof item.inside_change_score !== "number"
    || typeof item.minimum_inside_change !== "number"
    || typeof item.insufficient_change_inside_bbox !== "boolean"
    || (item.outside_change_regions !== undefined && !Array.isArray(item.outside_change_regions))
    || typeof item.notes !== "string") {
    throw new Error("Image job service returned an invalid guard result");
  }
  return {
    passed: item.passed,
    outsideChangeScore: item.outside_change_score,
    threshold: item.threshold,
    changedOutsideBBox: item.changed_outside_bbox,
    insideChangeScore: item.inside_change_score,
    minimumInsideChange: item.minimum_inside_change,
    insufficientChangeInsideBBox: item.insufficient_change_inside_bbox,
    outsideChangeRegions: (item.outside_change_regions ?? []).map((region) => parseBBox(region)).filter(
      (region): region is NormalizedBBox => region !== null,
    ),
    notes: item.notes,
  };
}

function isImageJobStage(value: unknown): value is ImageJobStage {
  return typeof value === "string" && imageJobStages.includes(value as ImageJobStage);
}

function isGeneratedImageUrl(imageUrl: string): boolean {
  try {
    return new URL(imageUrl, window.location.origin).pathname.startsWith("/api/v1/generated-images/");
  } catch {
    return false;
  }
}

export async function createImageJob(prompt: string, signal: AbortSignal): Promise<ImageJob> {
  const response = await fetch("/api/v1/image-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal,
  });

  return parseImageJobResponse(response);
}

export async function getImageJob(jobId: string, signal: AbortSignal): Promise<ImageJob> {
  const response = await fetch(`/api/v1/image-jobs/${encodeURIComponent(jobId)}`, { signal });
  return parseImageJobResponse(response);
}

export async function cancelImageJob(jobId: string): Promise<void> {
  const response = await fetch(`/api/v1/image-jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new ImageJobRequestError(
      await getImageJobErrorMessage(response),
      response.status,
    );
  }
}

export async function editImageJob(
  jobId: string, targetImageId: string, bbox: NormalizedBBox, userEditRequest: string, signal: AbortSignal,
): Promise<ImageJob> {
  const response = await fetch(`/api/v1/image-jobs/${encodeURIComponent(jobId)}/edits`, {
    method: "POST", headers: { "Content-Type": "application/json" }, signal,
    body: JSON.stringify({ target_image_id: targetImageId, bbox, user_edit_request: userEditRequest }),
  });
  return parseImageJobResponse(response);
}

export async function acceptImageJob(jobId: string): Promise<void> {
  const response = await fetch(`/api/v1/image-jobs/${encodeURIComponent(jobId)}/accept`, { method: "POST" });
  if (!response.ok) throw new ImageJobRequestError(await getImageJobErrorMessage(response), response.status);
}

export async function restorePreviousImageJob(jobId: string, targetImageId: string): Promise<ImageJob> {
  const response = await fetch(`/api/v1/image-jobs/${encodeURIComponent(jobId)}/restore-previous`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_image_id: targetImageId }),
  });
  return parseImageJobResponse(response);
}

export async function generateVisualization(_request: GenerationRequest): Promise<void> {
  // 保留的可视化生成服务入口，后续可接入真实生成 API。
  await delay(600);
}

export async function verifyScientificContent(_content: string): Promise<void> {
  // 扩展位置：接入权威文献检索、引用回溯和人工反馈修正流程。
  await delay(400);
}
