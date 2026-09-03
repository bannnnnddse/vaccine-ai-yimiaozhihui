import { describe, expect, it } from "vitest";
import { VIRUS_DIARY_IMAGE_BATCHES } from "./preloadVirusDiaryAssets";

describe("virus diary image preload manifest", () => {
  it("keeps the three level-oriented batches free of duplicate URLs", () => {
    expect(VIRUS_DIARY_IMAGE_BATCHES).toHaveLength(3);

    const urls = VIRUS_DIARY_IMAGE_BATCHES.flat();
    expect(new Set(urls).size).toBe(urls.length);
  });

  it("prioritizes the first visible background and level-one characters", () => {
    const firstBatch = VIRUS_DIARY_IMAGE_BATCHES[0].join(" ");
    expect(firstBatch).toContain("lymph-background.png");
    expect(firstBatch).toContain("maze-virus.png");
    expect(firstBatch).toContain("maze-dendritic-cell.png");
  });
});
