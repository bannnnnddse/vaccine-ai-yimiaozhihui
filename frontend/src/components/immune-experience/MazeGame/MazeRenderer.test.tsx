import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { DendriticAI } from "./DendriticAI";
import { MAZE, DENDRITIC_START, VIRUS_START } from "./mazeMap";
import { getMazeBoardLayout, MazeRenderer } from "./MazeRenderer";
import { VirusPlayer } from "./VirusPlayer";

const styles = readFileSync(new URL("../../../styles.css", import.meta.url), "utf8");
const visualTuningStyles = readFileSync(new URL("../../../immune-visual-tuning.css", import.meta.url), "utf8");

describe("MazeRenderer", () => {
  it("renders merged wall regions and keeps both actors on passage centers", () => {
    const html = renderToStaticMarkup(
      <MazeRenderer map={MAZE}>
        <VirusPlayer node={VIRUS_START} />
        <DendriticAI node={DENDRITIC_START} />
      </MazeRenderer>,
    );

    expect(html).toContain('data-maze-columns="21"');
    expect(html).toContain('data-maze-rows="13"');
    expect(html).toContain("data-maze-wall-region");
    expect(html).not.toContain("is-horizontal");
    expect(html).not.toContain("height:2px");
    expect(html).toMatch(/data-maze-virus="idle"[^>]*data-maze-node="r2c1"/);
    expect(html).toMatch(/data-maze-dendritic="idle"[^>]*data-maze-node="r1c1"/);
    expect(html).toContain("left:7.142857142857142%");
    expect(html).toContain("top:11.538461538461538%");
  });

  it("fits square 21 by 13 cells into landscape and portrait stages", () => {
    expect(getMazeBoardLayout(MAZE, { width: 1000, height: 800 })).toEqual({
      cellSize: 1000 / 21,
      width: 1000,
      height: (1000 / 21) * 13,
      left: 0,
      top: (800 - (1000 / 21) * 13) / 2,
    });
    expect(getMazeBoardLayout(MAZE, { width: 360, height: 720 })).toEqual({
      cellSize: 360 / 21,
      width: 360,
      height: (360 / 21) * 13,
      left: 0,
      top: (720 - (360 / 21) * 13) / 2,
    });
    expect(getMazeBoardLayout(MAZE, { width: 1200, height: 500 })).toEqual({
      cellSize: 500 / 13,
      width: (500 / 13) * 21,
      height: 500,
      left: (1200 - (500 / 13) * 21) / 2,
      top: 0,
    });
  });

  it("uses the entire immersive canvas for the maze without an inset shell", () => {
    expect(styles).toMatch(
      /\.full-page-experience--immune\s+\.immune-maze\s*{[^}]*left:\s*0;[^}]*top:\s*0;[^}]*width:\s*100%;[^}]*height:\s*100%;[^}]*aspect-ratio:\s*auto;[^}]*transform:\s*none;[^}]*border-radius:\s*0;/s,
    );
    expect(styles).toMatch(
      /\.full-page-experience--immune\s+\.immune-capture-animation-scene\s+\.immune-capture-stage\s*{[^}]*border-radius:\s*0;/s,
    );
  });

  it("exposes visual-only dendritic offsets without changing maze node coordinates", () => {
    expect(styles).toMatch(
      /\.immune-maze-game\s*{[^}]*--immune-maze-dendritic-offset-x:\s*8px;[^}]*--immune-maze-dendritic-offset-y:\s*0px;/s,
    );
    const html = renderToStaticMarkup(
      <MazeRenderer map={MAZE}>
        <DendriticAI node={DENDRITIC_START} />
      </MazeRenderer>,
    );
    expect(html).toContain("var(--immune-maze-dendritic-offset-x)");
    expect(html).toContain("var(--immune-maze-dendritic-offset-y)");
  });

  it("exposes one global maze wall color and uses it directly", () => {
    expect(visualTuningStyles).toMatch(/:root\s*{[^}]*--immune-maze-wall-color:\s*#750013;/s);
    expect(styles).toMatch(/\.immune-maze__wall\s*{[^}]*background:\s*var\(--immune-maze-wall-color\)/s);
    expect(styles).not.toContain("color-mix(in srgb, var(--immune-maze-wall-color)");
  });
});
