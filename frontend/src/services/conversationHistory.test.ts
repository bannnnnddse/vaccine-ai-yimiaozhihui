import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  CONVERSATION_HISTORY_RETENTION_MS,
  CONVERSATION_HISTORY_STORAGE_KEY,
  fallbackConversationTitle,
  loadConversations,
  persistConversations,
  type StoredConversation,
} from "./conversationHistory";

const now = Date.UTC(2026, 7, 22, 12);

function conversation(id: string, updatedAt: number): StoredConversation {
  return {
    version: 1,
    id,
    title: `标题 ${id}`,
    titleStatus: "generated",
    createdAt: updatedAt - 1_000,
    updatedAt,
    mode: "chat",
    sessionId: `response-${id}`,
    messages: [{ id: `user-${id}`, role: "user", kind: "text", content: `问题 ${id}` }],
  };
}

describe("conversation history repository", () => {
  let storage: Map<string, string>;

  beforeEach(() => {
    storage = new Map();
    vi.stubGlobal("window", { localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
    } });
  });

  it("sorts by updatedAt and keeps the 6d23h boundary", () => {
    persistConversations([
      conversation("older", now - (6 * 24 + 23) * 60 * 60 * 1_000),
      conversation("newer", now - 1_000),
    ], now);

    expect(loadConversations(now).map((item) => item.id)).toEqual(["newer", "older"]);
  });

  it("removes conversations at and beyond seven days on initialization", () => {
    const envelope = {
      version: 1,
      conversations: [
        conversation("boundary", now - CONVERSATION_HISTORY_RETENTION_MS),
        conversation("expired", now - CONVERSATION_HISTORY_RETENTION_MS - 1),
        conversation("active", now - CONVERSATION_HISTORY_RETENTION_MS + 1),
      ],
    };
    storage.set(CONVERSATION_HISTORY_STORAGE_KEY, JSON.stringify(envelope));

    expect(loadConversations(now).map((item) => item.id)).toEqual(["active"]);
  });

  it("skips malformed records without breaking valid history", () => {
    storage.set(CONVERSATION_HISTORY_STORAGE_KEY, JSON.stringify({
      version: 1,
      conversations: [{ id: "broken" }, conversation("valid", now)],
    }));

    expect(loadConversations(now).map((item) => item.id)).toEqual(["valid"]);
  });

  it("normalizes and truncates fallback titles", () => {
    expect(fallbackConversationTitle("  我今年17岁，\n是男生，请问现在还能不能接种九价HPV疫苗？  "))
      .toBe("我今年17岁， 是男生，请问现在还能不能接种九…");
  });

  it("normalizes legacy mode ownership without merging unrelated conversations", () => {
    const chat = conversation("legacy-chat", now);
    const illustration = { ...conversation("legacy-image", now), mode: "illustration" };
    storage.set(CONVERSATION_HISTORY_STORAGE_KEY, JSON.stringify({ version: 1, conversations: [chat, illustration] }));
    const restored = loadConversations(now);
    expect(restored).toHaveLength(2);
    expect(restored.find((record) => record.id === chat.id)?.messages[0].mode).toBe("chat");
    expect(restored.find((record) => record.id === illustration.id)?.messages[0].mode).toBe("illustration");
  });

  it("round trips both modes under one ID and rejects invalid message modes", () => {
    const unified = conversation("unified", now);
    unified.messages = [
      { id: "chat", role: "user", kind: "text", content: "问答", mode: "chat" },
      { id: "image", role: "user", kind: "text", content: "图解", mode: "illustration" },
    ];
    persistConversations([unified], now);
    expect(loadConversations(now)[0].messages).toEqual(unified.messages);
    storage.set(CONVERSATION_HISTORY_STORAGE_KEY, JSON.stringify({ version: 1, conversations: [
      unified,
      { ...conversation("invalid", now), messages: [{ ...unified.messages[0], mode: "unknown" }] },
    ] }));
    expect(loadConversations(now).map((record) => record.id)).toEqual(["unified"]);
  });
});
