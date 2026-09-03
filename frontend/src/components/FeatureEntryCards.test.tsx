import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { FeatureEntryCards } from "./FeatureEntryCards";

describe("FeatureEntryCards", () => {
  it("shows the knowledge graph entry with existing feature cards", () => {
    const html = renderToStaticMarkup(
      <FeatureEntryCards onGraph={vi.fn()} onInteractive={vi.fn()} onVideo={vi.fn()} />,
    );
    expect(html).toContain("知识图谱");
    expect(html).toContain("查看图谱");
    expect(html).toContain("feature-card--graph");
  });
});
