import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { BCellDifferentiation } from "./BCellDifferentiation";

describe("BCellDifferentiation", () => {
  it("creates three memory B cells and five plasma cells during differentiation", () => {
    const markup = renderToStaticMarkup(<BCellDifferentiation phase="differentiation" />);

    expect(markup.match(/data-memory-b-cell=/g)).toHaveLength(3);
    expect(markup.match(/data-plasma-cell=/g)).toHaveLength(5);
    expect(markup.match(/记忆B细胞/g)).toHaveLength(3);
    expect(markup.match(/浆细胞/g)).toHaveLength(5);
    expect(markup).toContain("memory-b-cell.png");
    expect(markup).toContain("plasma-cell.png");
  });

  it("fades memory B cells before antibody production", () => {
    const markup = renderToStaticMarkup(<BCellDifferentiation phase="plasma-ready" />);

    expect(markup.match(/data-memory-b-cell=/g)).toHaveLength(3);
    expect(markup).toContain("is-memory-withdrawing");
    expect(markup).not.toContain("data-antibody-particle");
  });

  it("keeps five plasma cells and emits red antibodies in the finale", () => {
    const markup = renderToStaticMarkup(<BCellDifferentiation phase="antibody" />);

    expect(markup).not.toContain("data-memory-b-cell");
    expect(markup.match(/data-plasma-cell=/g)).toHaveLength(5);
    expect(markup.match(/data-antibody-particle=/g)).toHaveLength(60);
    expect(markup).toContain("e65b67");
  });

  it("hands later finale phases to virus neutralization after plasma cells disappear", () => {
    const markup = renderToStaticMarkup(<BCellDifferentiation phase="virus-entry" />);

    expect(markup).not.toContain("data-plasma-cell");
    expect(markup.match(/data-neutralization-virus=/g)).toHaveLength(4);
    expect(markup.match(/data-withdrawing-antibody=/g)).toHaveLength(60);
    expect(markup.match(/data-binding-antibody=/g)).toHaveLength(9);
  });

  it("uses transform-based contact, presentation, and differentiation motion with readable labels", () => {
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

    expect(styles).toContain("@keyframes immune-helper-to-b");
    expect(styles).toContain("@keyframes immune-antigen-presenter-cross");
    expect(styles).toContain("@keyframes immune-cell-differentiation-spread");
    expect(styles).toMatch(/\.immune-differentiated-cell__label\s*{[^}]*color:\s*#173f5d[^}]*background:\s*rgba\(255,255,255,\.9/s);
    expect(styles).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*\.immune-differentiated-cell/s);
  });
});
