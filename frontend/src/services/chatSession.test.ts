import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearChatSessionId,
  readChatSessionId,
  writeChatSessionId,
} from "./chatSession";

const storageKey = "vaccine-ai.chat-response-id";

function stubSessionStorage() {
  const values = new Map<string, string>();
  const sessionStorage = {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => values.set(key, value)),
    removeItem: vi.fn((key: string) => values.delete(key)),
  };
  vi.stubGlobal("window", { sessionStorage });
  return sessionStorage;
}

describe("chatSession", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads the session ID from sessionStorage", () => {
    const sessionStorage = stubSessionStorage();
    sessionStorage.getItem.mockReturnValue("session-1");

    expect(readChatSessionId()).toBe("session-1");
    expect(sessionStorage.getItem).toHaveBeenCalledWith(storageKey);
  });

  it("writes only the session ID to sessionStorage", () => {
    const sessionStorage = stubSessionStorage();

    writeChatSessionId("session-2");

    expect(sessionStorage.setItem).toHaveBeenCalledWith(storageKey, "session-2");
  });

  it("clears the session ID from sessionStorage", () => {
    const sessionStorage = stubSessionStorage();

    clearChatSessionId();

    expect(sessionStorage.removeItem).toHaveBeenCalledWith(storageKey);
  });

  it("returns null and ignores writes when window is unavailable", () => {
    vi.stubGlobal("window", undefined);

    expect(readChatSessionId()).toBeNull();
    expect(() => writeChatSessionId("session-3")).not.toThrow();
    expect(() => clearChatSessionId()).not.toThrow();
  });

  it("returns null and ignores writes when the sessionStorage getter throws", () => {
    const windowWithBlockedStorage = {};
    Object.defineProperty(windowWithBlockedStorage, "sessionStorage", {
      get: () => { throw new Error("blocked"); },
    });
    vi.stubGlobal("window", windowWithBlockedStorage);

    expect(readChatSessionId()).toBeNull();
    expect(() => writeChatSessionId("session-3")).not.toThrow();
    expect(() => clearChatSessionId()).not.toThrow();
  });

  it("returns null and ignores storage errors", () => {
    const sessionStorage = {
      getItem: vi.fn(() => { throw new Error("blocked"); }),
      setItem: vi.fn(() => { throw new Error("blocked"); }),
      removeItem: vi.fn(() => { throw new Error("blocked"); }),
    };
    vi.stubGlobal("window", { sessionStorage });

    expect(readChatSessionId()).toBeNull();
    expect(() => writeChatSessionId("session-3")).not.toThrow();
    expect(() => clearChatSessionId()).not.toThrow();
  });
});
