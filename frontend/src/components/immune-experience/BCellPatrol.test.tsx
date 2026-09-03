import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { BCellPatrol } from "./BCellPatrol";

describe("BCellPatrol", () => {
  it("turns from the activated B-cell asset to the patrol-facing asset during the intro", () => {
    const markup = renderToStaticMarkup(<BCellPatrol phase="b-cell-patrol-intro" />);

    expect(markup).toContain("data-patrol-b-cell-turn");
    expect(markup).toContain(level3Assets.bCell);
    expect(markup).toContain(level3Assets.bCellPatrol);
    expect(markup).toContain("is-before");
    expect(markup).toContain("is-after");
  });

  it("uses the patrol-facing B cell and requested virus asset during patrol", () => {
    const markup = renderToStaticMarkup(<BCellPatrol phase="b-cell-patrol-caught" />);

    expect(markup).toContain(level3Assets.bCellPatrol);
    expect(markup).toContain(level3Assets.patrolVirus);
    expect(markup.match(/class="immune-b-cell-patrol__virus/g)).toHaveLength(3);
    expect(markup).toContain("抓到你了！我已被活化！开始分化！");
  });

  it("defines the two-face turn and a reduced-motion final orientation", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../../styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toMatch(/\.immune-b-cell-patrol__turn-face\.is-before\s*{[^}]*immune-patrol-b-turn-out\s+300ms/s);
    expect(styles).toMatch(/\.immune-b-cell-patrol__turn-face\.is-after\s*{[^}]*immune-patrol-b-turn-in\s+300ms[^}]*300ms/s);
    expect(styles).toMatch(/@keyframes immune-patrol-b-turn-out\s*{[^}]*rotateY\(0\)[^}]*}[^}]*rotateY\(90deg\)/s);
    expect(styles).toMatch(/@keyframes immune-patrol-b-turn-in\s*{[^}]*rotateY\(-90deg\)[^}]*}[^}]*rotateY\(0\)/s);
    expect(styles).toMatch(/\.immune-b-cell-patrol__turn-face\.is-after\s*{\s*opacity:\s*1;\s*transform:\s*none;/s);
  });

  it("enlarges every asset and exposes both caught-state endpoints", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../../styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toMatch(/--immune-patrol-caught-b-cell-left:\s*[-\d.]+%/);
    expect(styles).toMatch(/--immune-patrol-caught-b-cell-top:\s*[-\d.]+%/);
    expect(styles).toMatch(/--immune-patrol-caught-virus-left:\s*[-\d.]+%/);
    expect(styles).toMatch(/--immune-patrol-caught-virus-top:\s*[-\d.]+%/);
    expect(styles).toContain("--immune-patrol-b-cell-size: clamp(230.88px, 28.08vw, 349.44px)");
    expect(styles).toContain("--immune-patrol-helper-cell-size: clamp(193.44px, 23.4vw, 302.64px)");
    expect(styles).toContain("--immune-patrol-virus-size: clamp(65.52px, 7.8vw, 106.08px)");
    expect(styles).toMatch(/\.immune-b-cell-patrol__departing-b\s*{[^}]*var\(--immune-patrol-b-cell-size\)/s);
    expect(styles).toMatch(/\.immune-b-cell-patrol__departing-helper[^}]*var\(--immune-patrol-helper-cell-size\)/s);
    expect(styles).toMatch(/\.immune-b-cell-patrol__virus\s*{[^}]*var\(--immune-patrol-virus-size\)/s);
    expect(styles).toMatch(/\.immune-b-cell-patrol__b-cell\s*{[^}]*var\(--immune-patrol-b-cell-size\)/s);
    expect(styles).toMatch(/\.immune-b-cell-patrol\.is-caught \.immune-b-cell-patrol__b-cell\s*{[^}]*var\(--immune-patrol-caught-b-cell-left\)[^}]*var\(--immune-patrol-caught-b-cell-top\)/s);
    expect(styles).toMatch(/\.immune-b-cell-patrol__virus\.is-virus-2\s*{[^}]*left:\s*var\(--immune-patrol-caught-virus-left\)[^}]*top:\s*var\(--immune-patrol-caught-virus-top\)/s);
    expect(styles).toMatch(/\.immune-b-cell-patrol\.is-caught \.immune-b-cell-patrol__virus\.is-virus-2\s*{[^}]*animation:\s*none[^}]*transform:\s*none/s);
    expect(styles).not.toContain("--immune-patrol-virus-2-left");
    expect(styles).not.toContain("--immune-patrol-virus-2-top");
    expect(styles).toMatch(/@keyframes immune-patrol-b-move[^]*100%\s*{[^}]*left:\s*var\(--immune-patrol-caught-b-cell-left\)[^}]*top:\s*var\(--immune-patrol-caught-b-cell-top\)/s);
    expect(styles).not.toContain("translate3d(calc(-50% - 45vw)");
  });
});
