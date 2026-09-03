import { afterEach, describe, expect, it, vi } from "vitest";
import {
  IMAGE_HISTORY_STORAGE_KEY,
  IMAGE_HISTORY_TTL_MS,
  loadImageHistory,
  saveImageHistoryEntry,
} from "./imageHistory";

afterEach(() => vi.unstubAllGlobals());

function installStorage(initial: Record<string, string> = {}) {
  const storage = new Map(Object.entries(initial));
  vi.stubGlobal("window", { localStorage: {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  } });
  return storage;
}

function draft(imageId = "job-1-v0") {
  return {
    prompt: "免疫记忆",
    jobId: "job-1",
    imageUrl: `/api/v1/generated-images/${imageId}.png`,
    imageId,
    autoRevisionCount: 0,
    revisionOrigin: "initial" as const,
    traceId: `trace-${imageId}`,
    traceEvents: [{
      id: `trace-${imageId}-1`, stage: "completed" as const, title: "图解已准备完成",
      status: "completed" as const, createdAt: "2026-08-13T10:00:00Z",
    }],
  };
}

describe("image history persistence", () => {
  it("stores newest entries first and replaces the same image version", () => {
    installStorage();
    const now = Date.parse("2026-08-14T09:00:00Z");
    saveImageHistoryEntry(draft("job-1-v0"), now);
    saveImageHistoryEntry(draft("job-1-v1"), now + 1_000);
    saveImageHistoryEntry({ ...draft("job-1-v0"), prompt: "更新后的标题" }, now + 2_000);

    const entries = loadImageHistory(now + 2_000);
    expect(entries.map((entry) => entry.imageId)).toEqual(["job-1-v0", "job-1-v1"]);
    expect(entries[0]).toMatchObject({ prompt: "更新后的标题", expiresAt: now + 2_000 + IMAGE_HISTORY_TTL_MS });
  });

  it("removes each entry after its own 24 hour lifetime", () => {
    const storage = installStorage();
    const now = Date.parse("2026-08-14T10:00:00Z");
    saveImageHistoryEntry(draft(), now);

    expect(loadImageHistory(now + IMAGE_HISTORY_TTL_MS - 1)).toHaveLength(1);
    expect(loadImageHistory(now + IMAGE_HISTORY_TTL_MS)).toEqual([]);
    expect(JSON.parse(storage.get(IMAGE_HISTORY_STORAGE_KEY) ?? "null")).toEqual([]);
  });

  it("migrates valid recent image results without restoring chat messages", () => {
    const now = Date.parse("2026-08-14T09:00:00Z");
    const legacy = [
      { id: "user-1", role: "user", kind: "text", content: "免疫记忆" },
      { id: "result-1", role: "assistant", kind: "image-result", stage: "completed", requestToken: "request-1", ...draft() },
    ];
    const storage = installStorage({ "vaccine-ai.image-conversation.v1": JSON.stringify(legacy) });

    const entries = loadImageHistory(now);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ imageId: "job-1-v0", prompt: "免疫记忆" });
    expect(storage.has("vaccine-ai.image-conversation.v1")).toBe(false);
  });

  it("rejects malformed and external image records", () => {
    installStorage({
      [IMAGE_HISTORY_STORAGE_KEY]: JSON.stringify([{ ...draft(), id: "bad", createdAt: 1, expiresAt: Number.MAX_SAFE_INTEGER, imageUrl: "https://example.com/untrusted.png" }]),
    });
    expect(loadImageHistory(2)).toEqual([]);
  });

  it("keeps the live return value when storage is unavailable", () => {
    vi.stubGlobal("window", { localStorage: {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
      removeItem: () => { throw new Error("blocked"); },
    } });
    expect(saveImageHistoryEntry(draft(), 100)).toHaveLength(1);
  });
});
