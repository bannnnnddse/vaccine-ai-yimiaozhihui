const chatSessionStorageKey = "vaccine-ai.chat-response-id";

function getSessionStorage(): Storage | null {
  if (typeof window === "undefined") return null;

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function readChatSessionId(): string | null {
  try {
    return getSessionStorage()?.getItem(chatSessionStorageKey) ?? null;
  } catch {
    return null;
  }
}

export function writeChatSessionId(sessionId: string): void {
  try {
    getSessionStorage()?.setItem(chatSessionStorageKey, sessionId);
  } catch {
    // Storage can be disabled by browser privacy settings.
  }
}

export function clearChatSessionId(): void {
  try {
    getSessionStorage()?.removeItem(chatSessionStorageKey);
  } catch {
    // Storage can be disabled by browser privacy settings.
  }
}
