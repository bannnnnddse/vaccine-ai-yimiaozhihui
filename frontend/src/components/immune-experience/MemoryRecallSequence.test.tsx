import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import {
  createMemoryRecallAntibodies,
  MemoryRecallSequence,
} from "./MemoryRecallSequence";

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

describe("createMemoryRecallAntibodies", () => {
  it("creates 240 deterministic particles with a broadly distributed layout", () => {
    const first = createMemoryRecallAntibodies();

    expect(first).toHaveLength(240);
    expect(createMemoryRecallAntibodies()).toEqual(first);
    expect(new Set(first.map((particle) => `${particle.x}:${particle.y}`)).size).toBe(240);
  });
});

describe("MemoryRecallSequence", () => {
  it("shows three staggered viruses and the sleeping memory cell during recall", () => {
    const markup = renderToStaticMarkup(<MemoryRecallSequence phase="memory-recall" />);

    expect(markup.match(/data-recall-virus=/g)).toHaveLength(3);
    expect(markup).toContain("sleeping-memory-b-cell.png");
    expect(markup).not.toContain("data-recall-antibody");
  });

  it("keeps both memory-cell layers mounted for the awakening crossfade", () => {
    const markup = renderToStaticMarkup(<MemoryRecallSequence phase="memory-awakening" />);

    expect(markup).toContain("sleeping-memory-b-cell.png");
    expect(markup).toContain("angry-memory-b-cell.png");
    expect(markup.match(/data-recall-virus=/g)).toHaveLength(3);
  });

  it("keeps every virus beyond the memory-cell safety radius at 320 by 568", () => {
    const viewport = { width: 320, height: 568 };
    const cell = {
      x: viewport.width * 0.76,
      y: viewport.height * 0.5,
      radius: Math.max(91.8, Math.min(viewport.width * 0.238, 127.5)),
    };
    const safetyGap = 16;
    const virusRadius = Math.max(18.7, Math.min(viewport.width * 0.0255, 32.3));
    const markup = renderToStaticMarkup(<MemoryRecallSequence phase="memory-recall" />);
    const trackStyles = [...markup.matchAll(/data-recall-virus="\d+"[^>]*style="([^"]+)"/g)]
      .map((match) => match[1]);

    expect(trackStyles).toHaveLength(3);
    trackStyles.forEach((style) => {
      const xToken = style.match(/--recall-virus-end-x:([^;]+)/)?.[1];
      const endY = Number(style.match(/--recall-virus-end-y:([\d.]+)vh/)?.[1]);
      expect(xToken).toBeTruthy();
      expect(endY).not.toBeNaN();

      const endX = xToken?.endsWith("px")
        ? cell.x - cell.radius - safetyGap - Number.parseFloat(xToken)
        : viewport.width * (Number.parseFloat(xToken ?? "0") / 100) + virusRadius;
      const distance = Math.hypot(endX - cell.x, viewport.height * (endY / 100) - cell.y);

      expect(distance).toBeGreaterThan(cell.radius + safetyGap);
    });

    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");
    expect(styles).toMatch(/\.immune-level-three\s*{[^}]*--memory-cell-center-x:\s*78vw[^}]*--memory-cell-center-y:\s*50vh/s);
    expect(styles).toMatch(/\.immune-level-three\s*{[^}]*--memory-cell-radius:\s*clamp\(107\.1px,\s*16\.15vw,\s*195\.5px\)[^}]*--memory-virus-size:\s*clamp\(47\.6px,\s*6\.8vw,\s*91\.8px\)/s);
    expect(styles).toMatch(/\.immune-level-three\s*{[^}]*--memory-virus-group-x:\s*0vw[^}]*--memory-virus-group-y:\s*0vh/s);
    expect(styles).toMatch(/\.immune-memory-recall,\s*\.immune-iris-transition\s*{[^}]*position:\s*fixed[^}]*inset:\s*0/s);
    expect(styles).toMatch(/\.immune-memory-recall__cell\s*{[^}]*left:\s*var\(--memory-cell-center-x\)[^}]*top:\s*var\(--memory-cell-center-y\)/s);
    expect(styles).toContain("--memory-cell-radius");
    expect(styles).toContain("--memory-virus-safety-gap");
    expect(styles).toContain("var(--memory-virus-safe-x)");
  });

  it("shows the angry cell and exactly 240 decorative antibodies during the storm", () => {
    const markup = renderToStaticMarkup(<MemoryRecallSequence phase="memory-antibody-storm" />);
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

    expect(markup).toContain("angry-memory-b-cell.png");
    expect(markup.match(/data-recall-antibody=/g)).toHaveLength(240);
    expect(markup.match(/data-recall-antibody=[^>]*aria-hidden="true"/g)).toHaveLength(240);
    expect(markup).not.toMatch(/data-recall-antibody=[^>]*alt="[^"]+"/);
    expect(markup).toContain("%23e65b67");
    expect(markup).toContain("var(--memory-antibody-size-scale)");
    expect(styles).toContain("--memory-antibody-size-scale: 1.3");
  });

  it("uses transform and opacity animations without interval-driven motion", () => {
    const source = readFileSync(new URL("./MemoryRecallSequence.tsx", import.meta.url), "utf8");
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

    expect(source).not.toContain("setInterval");
    expect(styles).toContain("transition: opacity 600ms");
    expect(styles).toContain("@keyframes immune-memory-virus-approach");
    expect(styles).toContain("@keyframes immune-memory-antibody-storm");
    const animatedDeclarations = styles
      .split("@keyframes immune-memory-virus-approach")[1]
      .split("@media (max-width: 720px)")[0];
    expect(animatedDeclarations).not.toMatch(/\b(?:left|top|width|height)\s*:/);
  });

  it("shrinks recall assets on mobile and resolves motion to stable end states", () => {
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");
    const mobileBlocks = extractMediaBlocks(styles, "@media (max-width: 720px)");
    const recallMobileBlock = mobileBlocks
      .filter((block) => block.includes(".immune-memory-recall") || block.includes("--memory-cell-center-x") || block.includes("--memory-cell-radius"))
      .join("\n");
    const reducedMotionBlocks = extractMediaBlocks(styles, "@media (prefers-reduced-motion: reduce)");
    const recallReducedMotionBlock = reducedMotionBlocks
      .filter((block) => block.includes(".immune-memory-recall"))
      .join("\n");

    expect(recallMobileBlock).not.toBe("");
    expect(recallMobileBlock).toMatch(/\.immune-level-three\s*{[^}]*--memory-cell-center-x:\s*76vw/s);
    expect(recallMobileBlock).toMatch(/\.immune-level-three\s*{[^}]*--memory-cell-radius:\s*clamp\(91\.8px,\s*23\.8vw,\s*127\.5px\)[^}]*--memory-virus-size:\s*clamp\(37\.4px,\s*5\.1vw,\s*64\.6px\)/s);
    expect(recallReducedMotionBlock).not.toBe("");
    expect(recallReducedMotionBlock).toMatch(/\.immune-memory-recall\s+\.immune-memory-recall__cell-layer\s*{[^}]*transition-duration:\s*\.01ms/s);
    expect(recallReducedMotionBlock).toMatch(/\.immune-memory-recall__virus\s*{[^}]*animation:\s*none[^}]*opacity:\s*1[^}]*transform:\s*translate3d\(calc\(var\(--memory-virus-safe-x\)/s);
    expect(recallReducedMotionBlock).toMatch(/\.immune-memory-recall__antibody\s*{[^}]*animation:\s*immune-memory-antibody-fade 120ms[^}]*transform:\s*translate3d\(calc\(var\(--recall-antibody-x\)/s);
    expect(styles).toMatch(/@keyframes immune-memory-antibody-fade\s*{\s*from\s*{\s*opacity:\s*0;?\s*}\s*to\s*{\s*opacity:\s*\.72;?\s*}\s*}/s);
  });
});
