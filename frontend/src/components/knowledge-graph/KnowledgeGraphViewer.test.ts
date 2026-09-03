import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { toCytoscapeElements } from "./KnowledgeGraphViewer";

describe("KnowledgeGraphViewer element mapping", () => {
  it("renders the graph exploration subtitle as smaller gray supporting text", () => {
    const source = readFileSync(new URL("./KnowledgeGraphViewer.tsx", import.meta.url), "utf8");
    const styles = readFileSync(new URL("./KnowledgeGraphViewer.css", import.meta.url), "utf8");

    expect(source).toContain("输入想了解的内容，一键展开相关知识网络");
    expect(styles).toMatch(/\.kg-title-row p\s*{[^}]*color:#697171;[^}]*font:\s*500 \.56em\/1\.25/s);
    expect(styles).toMatch(/\.kg-title-row p\s*{[^}]*background:none;[^}]*-webkit-text-fill-color:#697171;[^}]*text-shadow:none/s);
  });

  it("keeps stable ids, directed endpoints, labels, colors and circular shapes", () => {
    const elements = toCytoscapeElements({
      version: "graph-v2", knowledge_base_version: "kb-v2", center_id: "vaccine",
      depth: 1, truncated: false,
      nodes: [
        { id: "vaccine", label: "HPV疫苗", type: "Vaccine", aliases: [], degree: 1, source_count: 1 },
        { id: "virus", label: "HPV16", type: "Pathogen", aliases: [], degree: 1, source_count: 1 },
      ],
      edges: [{ id: "edge-1", source: "vaccine", target: "virus", relation: "PREVENTS", relation_label: "预防", confidence: 0.97, source_count: 1 }],
    });
    expect(elements[0].data).toMatchObject({ id: "vaccine", shape: "ellipse" });
    expect(elements[1].data).toMatchObject({ id: "virus", shape: "ellipse" });
    expect(elements[2].data).toMatchObject({ source: "vaccine", target: "virus", label: "预防" });
  });
});
