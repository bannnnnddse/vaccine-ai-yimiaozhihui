import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { IrisTransition } from "./IrisTransition";

const PHASES = ["iris-focus", "iris-hold", "iris-close", "blackout"] as const;

function extractMediaBlocks(styles: string, query: string): string[] {
  const blocks: string[] = [];
  let cursor = 0;

  while ((cursor = styles.indexOf(query, cursor)) !== -1) {
    const openingBrace = styles.indexOf("{", cursor + query.length);
    if (openingBrace === -1) break;

    let depth = 1;
    let end = openingBrace + 1;
    while (end < styles.length && depth > 0) {
      if (styles[end] === "{") depth += 1;
      if (styles[end] === "}") depth -= 1;
      end += 1;
    }

    blocks.push(styles.slice(cursor, end));
    cursor = end;
  }

  return blocks;
}

describe("IrisTransition", () => {
  it.each(PHASES)("renders the %s phase as an aria-hidden overlay", (phase) => {
    const markup = renderToStaticMarkup(<IrisTransition phase={phase} />);

    expect(markup).toContain('data-iris-transition="true"');
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain(`is-${phase}`);
    expect(markup.match(/immune-iris-transition__aperture/g)).toHaveLength(1);
  });

  it("defines a circular, memory-cell-aligned aperture for every ending phase", () => {
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

    expect(styles).toMatch(/\.immune-level-three\s*{[^}]*--memory-cell-center-x:\s*78vw[^}]*--memory-cell-center-y:\s*50vh/s);
    expect(styles).toMatch(/\.immune-memory-recall,\s*\.immune-iris-transition\s*{[^}]*position:\s*fixed[^}]*inset:\s*0/s);
    expect(styles).toMatch(/\.immune-memory-recall__cell\s*{[^}]*left:\s*var\(--memory-cell-center-x\)[^}]*top:\s*var\(--memory-cell-center-y\)/s);
    expect(styles).toMatch(/\.immune-iris-transition__aperture\s*{[^}]*left:\s*var\(--memory-cell-center-x\)[^}]*top:\s*var\(--memory-cell-center-y\)[^}]*border-radius:\s*50%[^}]*box-shadow:\s*0 0 0 200vmax #000/s);
    expect(styles).not.toContain("--memory-cell-x");
    expect(styles).not.toContain("--memory-cell-y");
    expect(styles).toContain("@keyframes immune-iris-focus");
    expect(styles).toMatch(/\.immune-iris-transition\.is-iris-focus\s+\.immune-iris-transition__aperture\s*{[^}]*animation:\s*immune-iris-focus 1400ms/s);
    expect(styles).toMatch(/\.immune-iris-transition\.is-iris-hold\s+\.immune-iris-transition__aperture\s*{[^}]*width:\s*clamp\(160px, 22vw, 250px\)[^}]*animation:\s*none/s);
    expect(styles).toContain("@keyframes immune-iris-close");
    expect(styles).toMatch(/\.immune-iris-transition\.is-iris-close\s+\.immune-iris-transition__aperture\s*{[^}]*animation:\s*immune-iris-close 650ms/s);
    expect(styles).toMatch(/\.immune-iris-transition\.is-blackout\s*{[^}]*background:\s*#000/s);
    expect(styles).toMatch(/\.immune-iris-transition\.is-blackout\s+\.immune-iris-transition__aperture\s*{[^}]*width:\s*0[^}]*height:\s*0/s);
  });

  it("removes the large iris travel while preserving an immediate solid-black ending", () => {
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");
    const reducedMotionBlocks = extractMediaBlocks(styles, "@media (prefers-reduced-motion: reduce)");
    const irisReducedMotionBlock = reducedMotionBlocks.find((block) => block.includes(".immune-iris-transition"));

    expect(irisReducedMotionBlock).toBeDefined();
    expect(irisReducedMotionBlock).toMatch(/\.immune-iris-transition\.is-iris-focus\s+\.immune-iris-transition__aperture\s*{[^}]*animation:\s*none[^}]*width:\s*clamp\(160px,\s*22vw,\s*250px\)/s);
    expect(irisReducedMotionBlock).toMatch(/\.immune-iris-transition\.is-iris-close\s*{[^}]*background:\s*#000/s);
    expect(irisReducedMotionBlock).toMatch(/\.immune-iris-transition\.is-iris-close\s+\.immune-iris-transition__aperture\s*{[^}]*animation:\s*none[^}]*width:\s*0[^}]*height:\s*0/s);
  });
});
