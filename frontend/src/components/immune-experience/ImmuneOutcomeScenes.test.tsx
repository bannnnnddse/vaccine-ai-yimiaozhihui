import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { IMMUNE_OUTCOME_SCENES, ImmuneOutcomeScenes } from "./ImmuneOutcomeScenes";

describe("ImmuneOutcomeScenes", () => {
  it("renders exactly three animated outcomes with two antibodies each", () => {
    const markup = renderToStaticMarkup(<ImmuneOutcomeScenes phase="outcome-scenes" />);

    expect(IMMUNE_OUTCOME_SCENES.map((scene) => scene.title)).toEqual([
      "被吞噬清除",
      "激活补体裂解",
      "中和失活",
    ]);
    expect(markup.match(/data-outcome-scene=/g)).toHaveLength(3);
    expect(markup.match(/data-outcome-antibody=/g)).toHaveLength(6);
    expect(markup).toContain("病毒的三个结局");
    expect(markup).not.toContain("凝集清除");
    expect(markup).not.toContain("吞噬细胞通过");
  });

  it("uses the original virus and antibody plus every generated state asset", () => {
    const markup = renderToStaticMarkup(<ImmuneOutcomeScenes phase="outcome-scenes" />);

    for (const asset of [
      level3Assets.virus,
      level3Assets.outcomeMacrophage,
      level3Assets.outcomeVirusRuptured,
      level3Assets.outcomeVirusNauseated,
      level3Assets.outcomeVirusDead,
    ]) {
      expect(markup).toContain(asset);
    }
    expect(markup).toContain("%23e65b67");
  });

  it("marks the exit phase and defines the three-row, one-shot animation system", () => {
    const exitMarkup = renderToStaticMarkup(<ImmuneOutcomeScenes phase="outcome-exit" />);
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

    expect(exitMarkup).toContain("is-exiting");
    expect(styles).toMatch(/\.immune-outcome-scenes\s*{[^}]*grid-template-rows:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/s);
    expect(styles).toContain("--immune-outcome-divider-width: 8px");
    for (const outcome of ["phagocytosis", "complement", "neutralization"]) {
      for (const antibody of [1, 2]) {
        expect(styles).toContain(`--immune-outcome-${outcome}-antibody-${antibody}-x:`);
        expect(styles).toContain(`--immune-outcome-${outcome}-antibody-${antibody}-y:`);
        expect(styles).toContain(`--immune-outcome-${outcome}-antibody-${antibody}-rotation:`);
      }
    }
    expect(styles).toContain("--immune-outcome-complement-antibody-1-fall-x:");
    expect(styles).toContain("--immune-outcome-complement-antibody-2-fall-y:");
    expect(styles.match(/antibody-1-x:\s*-320%/g)).toHaveLength(3);
    expect(styles.match(/antibody-1-rotation:\s*90deg/g)).toHaveLength(3);
    expect(styles.match(/antibody-2-x:\s*219%/g)).toHaveLength(3);
    expect(styles.match(/antibody-2-rotation:\s*-90deg/g)).toHaveLength(3);
    expect(styles).toMatch(/\.immune-outcome-scene \+ \.immune-outcome-scene\s*{[^}]*solid #000/s);
    expect(styles).toContain("@keyframes immune-outcome-title");
    expect(styles).toContain("@keyframes immune-outcome-macrophage-swallow");
    expect(styles).toContain("@keyframes immune-outcome-debris-burst");
    expect(styles).toContain("@keyframes immune-outcome-neutralization-dead");
    expect(styles).toMatch(/\.immune-outcome-scenes__title\s*{[^}]*animation:\s*immune-outcome-title 3s/s);
    expect(styles).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*\.immune-outcome-scenes__virus\.is-dead\s*{[^}]*opacity:\s*1/s);
  });
});
