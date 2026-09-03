import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import {
  TISSUE_NARRATION_HOLD_DURATION_MS,
  TISSUE_NARRATION_TEXT,
  TissueExploreScene,
} from "./TissueExploreScene";

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

describe("TissueExploreScene", () => {
  it("holds the completed narration for thirty seconds", () => {
    expect(TISSUE_NARRATION_HOLD_DURATION_MS).toBe(30_000);
  });

  it("breaks the narration into two lines after the comma", () => {
    expect(TISSUE_NARRATION_TEXT).toBe("病毒进入组织间隙后，\n首先会被树突状细胞追捕");

    const lineRule = styles.match(/\.immune-tissue-narration-scene__line\s*{([^}]*)}/s)?.[1] ?? "";
    expect(lineRule).toContain("white-space: pre-line");
  });

  it("first renders the centered tissue narration without mounting the maze", () => {
    const markup = renderToStaticMarkup(
      createElement(TissueExploreScene, { onCapture: () => undefined }),
    );

    expect(markup).toContain('class="immune-tissue-narration-scene"');
    expect(markup).toContain('aria-label="组织间隙追捕说明"');
    expect(markup).toContain(level3Assets.background);
    expect(markup).not.toContain('class="immune-maze-game"');
  });

  it("softens the lymph background with the same white haze as the prelude", () => {
    const hazeRule = styles.match(/\.immune-explore-stage::after\s*{([^}]*)}/s)?.[1] ?? "";

    expect(hazeRule).toContain("background: rgba(255,255,255,.35)");
    expect(hazeRule).toContain("backdrop-filter: blur(3px)");
  });
});
