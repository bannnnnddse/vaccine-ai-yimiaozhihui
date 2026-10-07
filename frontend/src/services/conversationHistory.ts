import type { ChatMode } from "../components/ChatInput";
import type { ChatMessageData } from "../components/ChatMessage";

export const CONVERSATION_HISTORY_STORAGE_KEY = "vaccine-ai.conversations.v1";
export const CONVERSATION_HISTORY_VERSION = 1 as const;
export const CONVERSATION_HISTORY_RETENTION_MS = 7 * 24 * 60 * 60 * 1_000;

export type ConversationTitleStatus = "pending" | "generated" | "fallback";

export interface StoredConversation {
  version: typeof CONVERSATION_HISTORY_VERSION;
  id: string;
  title: string;
  titleStatus: ConversationTitleStatus;
  createdAt: number;
  updatedAt: number;
  mode: ChatMode;
  sessionId: string | null;
  messages: ChatMessageData[];
}

interface StoredConversationEnvelope {
  version: typeof CONVERSATION_HISTORY_VERSION;
  conversations: StoredConversation[];
}

export function loadConversations(now = Date.now()): StoredConversation[] {
  const storage = getLocalStorage();
  if (!storage) return [];

  try {
    const raw = storage.getItem(CONVERSATION_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.version !== CONVERSATION_HISTORY_VERSION || !Array.isArray(parsed.conversations)) {
      return [];
    }
    const valid = parsed.conversations.filter(isStoredConversation);
    const active = sortConversations(valid.filter((conversation) => now - conversation.updatedAt < CONVERSATION_HISTORY_RETENTION_MS));
    if (active.length !== parsed.conversations.length) writeConversations(active, storage);
    return active;
  } catch {
    return [];
  }
}

export function persistConversations(
  conversations: StoredConversation[],
  now = Date.now(),
): StoredConversation[] {
  const active = sortConversations(conversations.filter((conversation) => (
    isStoredConversation(conversation)
    && now - conversation.updatedAt < CONVERSATION_HISTORY_RETENTION_MS
  )));
  const storage = getLocalStorage();
  if (storage) writeConversations(active, storage);
  return active;
}

export function fallbackConversationTitle(message: string): string {
  const normalized = message.replace(/\s+/g, " ").trim();
  if (!normalized) return "新对话";
  return Array.from(normalized).length > 24
    ? `${Array.from(normalized).slice(0, 23).join("")}…`
    : normalized;
}

export function createConversationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `conversation-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function writeConversations(conversations: StoredConversation[], storage: Storage): void {
  try {
    const envelope: StoredConversationEnvelope = {
      version: CONVERSATION_HISTORY_VERSION,
      conversations,
    };
    storage.setItem(CONVERSATION_HISTORY_STORAGE_KEY, JSON.stringify(envelope));
  } catch {
    // History is an optional local enhancement when storage is unavailable or full.
  }
}

function getLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function sortConversations(conversations: StoredConversation[]): StoredConversation[] {
  return [...conversations].sort((left, right) => right.updatedAt - left.updatedAt);
}

function isStoredConversation(value: unknown): value is StoredConversation {
  if (!isRecord(value)
    || value.version !== CONVERSATION_HISTORY_VERSION
    || typeof value.id !== "string" || !value.id.trim()
    || typeof value.title !== "string" || !value.title.trim()
    || !["pending", "generated", "fallback"].includes(String(value.titleStatus))
    || typeof value.createdAt !== "number" || !Number.isFinite(value.createdAt)
    || typeof value.updatedAt !== "number" || !Number.isFinite(value.updatedAt)
    || value.updatedAt < value.createdAt
    || !["chat", "illustration"].includes(String(value.mode))
    || (value.sessionId !== null && (typeof value.sessionId !== "string" || !value.sessionId.trim()))
    || !Array.isArray(value.messages) || value.messages.length === 0
    || !value.messages.every(isChatMessage)) {
    return false;
  }
  return value.messages.some((message) => message.role === "user" && message.kind === "text" && message.content.trim());
}

function isChatMessage(value: unknown): value is ChatMessageData {
  if (!isRecord(value)
    || typeof value.id !== "string" || !value.id.trim()
    || !["user", "assistant"].includes(String(value.role))) return false;

  if (value.kind === "text") {
    return typeof value.content === "string"
      && (value.isTyping === undefined || typeof value.isTyping === "boolean")
      && (value.sources === undefined || isJsonSafe(value.sources));
  }
  if (value.kind === "image-status") {
    return value.role === "assistant"
      && typeof value.prompt === "string"
      && (value.jobId === null || typeof value.jobId === "string")
      && typeof value.requestToken === "string"
      && typeof value.stage === "string"
      && Array.isArray(value.traceEvents)
      && isJsonSafe(value);
  }
  if (value.kind === "image-result") {
    return value.role === "assistant"
      && typeof value.prompt === "string"
      && typeof value.jobId === "string"
      && typeof value.requestToken === "string"
      && typeof value.imageUrl === "string"
      && typeof value.imageId === "string"
      && typeof value.stage === "string"
      && typeof value.autoRevisionCount === "number"
      && typeof value.traceId === "string"
      && Array.isArray(value.traceEvents)
      && isJsonSafe(value);
  }
  return false;
}

function isJsonSafe(value: unknown, seen = new Set<unknown>()): boolean {
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object" || seen.has(value)) return false;
  if (typeof Blob !== "undefined" && value instanceof Blob) return false;
  seen.add(value);
  const safe = Array.isArray(value)
    ? value.every((item) => isJsonSafe(item, seen))
    : Object.values(value as Record<string, unknown>).every((item) => item === undefined || isJsonSafe(item, seen));
  seen.delete(value);
  return safe;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
