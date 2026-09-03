import { afterEach, describe, expect, it, vi } from "vitest";
import { loginAdmin, publishKnowledgeGap, restoreAdminSession } from "./adminService";

describe("adminService", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("restores the server session and sends its CSRF token on publish", async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce({
        ok: true, status: 200,
        json: async () => ({ username: "admin", csrf_token: "csrf-value", expires_at: 123 }),
      })
      .mockResolvedValueOnce({
        ok: true, status: 200,
        json: async () => ({ gap: { id: "gap-1" }, audit_events: [] }),
      });
    vi.stubGlobal("fetch", fetchSpy);

    await restoreAdminSession();
    await publishKnowledgeGap("gap-1", 4);

    const publishInit = fetchSpy.mock.calls[1][1] as RequestInit;
    expect((publishInit.headers as Headers).get("X-CSRF-Token")).toBe("csrf-value");
    expect(publishInit.body).toBe(JSON.stringify({ version: 4 }));
  });

  it("does not persist or expose the administrator password", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ username: "admin", csrf_token: "csrf", expires_at: 123 }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await loginAdmin("admin", "private-password");

    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/admin/session", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ username: "admin", password: "private-password" }),
    }));
  });
});
