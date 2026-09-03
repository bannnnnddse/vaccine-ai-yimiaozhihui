import { afterEach, describe, expect, it, vi } from "vitest";
import { getGraphMeta, getKnowledgeGraph, searchKnowledgeGraph } from "./knowledgeGraphService";

describe("knowledgeGraphService", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("always reads metadata without browser cache", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        version: "graph-v2", knowledge_base_version: "kb-v2", updated_at: "2026-08-20T00:00:00Z",
        source_documents: 12, node_count: 20, edge_count: 30, schema_version: "v2", model: "qwen",
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await expect(getGraphMeta()).resolves.toMatchObject({ version: "graph-v2", node_count: 20 });
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/knowledge-graph/meta", expect.objectContaining({ cache: "no-store" }));
  });

  it("serializes ego depth and filters", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "graph-v2", knowledge_base_version: "kb-v2", center_id: "hpv", depth: 2, truncated: false, nodes: [], edges: [] }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await getKnowledgeGraph({ center: "HPV疫苗", depth: 2, types: ["Vaccine"], relations: ["PREVENTS"] });
    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toContain("center=HPV");
    expect(url).toContain("depth=2");
    expect(url).toContain("types=Vaccine");
    expect(url).toContain("relations=PREVENTS");
  });

  it("searches the complete graph rather than loaded elements", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "graph-v2", items: [{ id: "1", label: "HPV16", type: "Pathogen", matched_alias: "HPV-16" }] }),
    }));
    await expect(searchKnowledgeGraph("HPV-16")).resolves.toMatchObject({ items: [{ label: "HPV16" }] });
  });
});
