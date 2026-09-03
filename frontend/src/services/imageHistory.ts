import type { ImageResultChatMessage } from "../components/ChatMessage";
import type { ImageProcessEvent, RevisionOrigin } from "./generationService";

export const IMAGE_HISTORY_TTL_MS = 24 * 60 * 60 * 1000;
export const IMAGE_HISTORY_STORAGE_KEY = "vaccine-ai.image-history.v2";
const LEGACY_STORAGE_KEY = "vaccine-ai.image-conversation.v1";

export interface ImageHistoryEntry {
  id: string;
  imageId: string;
  imageUrl: string;
  jobId: string;
  prompt: string;
  autoRevisionCount: number;
  revisionOrigin?: RevisionOrigin;
  traceId: string;
  traceEvents: ImageProcessEvent[];
  createdAt: number;
  expiresAt: number;
}

export type ImageHistoryDraft = Pick<ImageResultChatMessage,
  "imageId" | "imageUrl" | "jobId" | "prompt" | "autoRevisionCount" | "revisionOrigin" | "traceId" | "traceEvents"
>;

export function loadImageHistory(now = Date.now()): ImageHistoryEntry[] {
  try {
    const stored = readStoredHistory();
    const migrated = stored.length === 0 ? migrateLegacyHistory(now) : [];
    const source = stored.length > 0 ? stored : migrated;
    const active = dedupe(source.filter((entry) => entry.expiresAt > now));
    if (active.length !== source.length || migrated.length > 0) writeHistory(active);
    removeLegacyHistory();
    return active;
  } catch {
    return [];
  }
}

export function saveImageHistoryEntry(
  draft: ImageHistoryDraft,
  now = Date.now(),
): ImageHistoryEntry[] {
  const current = loadImageHistory(now);
  const entry: ImageHistoryEntry = {
    id: `image-history-${draft.imageId}`,
    imageId: draft.imageId,
    imageUrl: draft.imageUrl,
    jobId: draft.jobId,
    prompt: draft.prompt,
    autoRevisionCount: draft.autoRevisionCount,
    ...(draft.revisionOrigin ? { revisionOrigin: draft.revisionOrigin } : {}),
    traceId: draft.traceId,
    traceEvents: draft.traceEvents,
    createdAt: now,
    expiresAt: now + IMAGE_HISTORY_TTL_MS,
  };
  const next = dedupe([entry, ...current.filter((item) => item.imageId !== entry.imageId)]);
  try {
    writeHistory(next);
  } catch {
    // The live result remains available when browser storage is blocked or full.
  }
  return next;
}

function readStoredHistory(): ImageHistoryEntry[] {
  const raw = window.localStorage?.getItem(IMAGE_HISTORY_STORAGE_KEY);
  if (!raw) return [];
  const value = JSON.parse(raw) as unknown;
  if (!Array.isArray(value)) return [];
  return value.filter(isHistoryEntry);
}

function migrateLegacyHistory(now: number): ImageHistoryEntry[] {
  const raw = window.localStorage?.getItem(LEGACY_STORAGE_KEY);
  if (!raw) return [];
  const value = JSON.parse(raw) as unknown;
  if (!Array.isArray(value)) return [];
  const entries: ImageHistoryEntry[] = [];
  for (const candidate of value) {
    if (!isLegacyImageResult(candidate)) continue;
    const timestamps = candidate.traceEvents
      .map((event) => Date.parse(event.createdAt))
      .filter(Number.isFinite);
    if (timestamps.length === 0) continue;
    const createdAt = Math.min(now, Math.max(...timestamps));
    const expiresAt = createdAt + IMAGE_HISTORY_TTL_MS;
    if (expiresAt <= now) continue;
    entries.push({
      id: `image-history-${candidate.imageId}`,
      imageId: candidate.imageId,
      imageUrl: candidate.imageUrl,
      jobId: candidate.jobId,
      prompt: candidate.prompt,
      autoRevisionCount: candidate.autoRevisionCount,
      ...(candidate.revisionOrigin ? { revisionOrigin: candidate.revisionOrigin } : {}),
      traceId: candidate.traceId,
      traceEvents: candidate.traceEvents,
      createdAt,
      expiresAt,
    });
  }
  return dedupe(entries);
}

function dedupe(entries: ImageHistoryEntry[]): ImageHistoryEntry[] {
  const seen = new Set<string>();
  return entries
    .sort((left, right) => right.createdAt - left.createdAt)
    .filter((entry) => {
      if (seen.has(entry.imageId)) return false;
      seen.add(entry.imageId);
      return true;
    });
}

function writeHistory(entries: ImageHistoryEntry[]): void {
  window.localStorage?.setItem?.(IMAGE_HISTORY_STORAGE_KEY, JSON.stringify(entries));
}

function removeLegacyHistory(): void {
  window.localStorage?.removeItem?.(LEGACY_STORAGE_KEY);
}

function isHistoryEntry(value: unknown): value is ImageHistoryEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Record<string, unknown>;
  return typeof entry.id === "string"
    && typeof entry.imageId === "string"
    && typeof entry.jobId === "string"
    && typeof entry.prompt === "string"
    && isGeneratedImageUrl(entry.imageUrl)
    && typeof entry.autoRevisionCount === "number"
    && isRevisionOrigin(entry.revisionOrigin)
    && typeof entry.traceId === "string"
    && isTraceEvents(entry.traceEvents)
    && typeof entry.createdAt === "number" && Number.isFinite(entry.createdAt)
    && typeof entry.expiresAt === "number" && Number.isFinite(entry.expiresAt);
}

function isLegacyImageResult(value: unknown): value is ImageHistoryDraft {
  if (!value || typeof value !== "object") return false;
  const message = value as Record<string, unknown>;
  return message.kind === "image-result"
    && typeof message.imageId === "string"
    && typeof message.jobId === "string"
    && typeof message.prompt === "string"
    && isGeneratedImageUrl(message.imageUrl)
    && typeof message.autoRevisionCount === "number"
    && isRevisionOrigin(message.revisionOrigin)
    && typeof message.traceId === "string"
    && isTraceEvents(message.traceEvents);
}

function isRevisionOrigin(value: unknown): value is RevisionOrigin | undefined {
  return value === undefined || value === "initial" || value === "auto" || value === "human";
}

function isGeneratedImageUrl(value: unknown): value is string {
  return typeof value === "string" && value.startsWith("/api/v1/generated-images/");
}

function isTraceEvents(value: unknown): value is ImageProcessEvent[] {
  return Array.isArray(value) && value.every((event) => {
    if (!event || typeof event !== "object") return false;
    const item = event as Record<string, unknown>;
    return typeof item.id === "string"
      && typeof item.stage === "string"
      && typeof item.title === "string"
      && typeof item.status === "string"
      && typeof item.createdAt === "string";
  });
}
