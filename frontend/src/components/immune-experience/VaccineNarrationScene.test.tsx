import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { HOLD_DURATION_MS, VaccineNarrationScene } from "./VaccineNarrationScene";

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

describe("VaccineNarrationScene", () => {
  it("holds each completed narration line for thirty seconds", () => {
    expect(HOLD_DURATION_MS).toBe(30_000);
  });

  it("keeps the narration surface directly interactive", () => {
    const markup = renderToStaticMarkup(<VaccineNarrationScene onComplete={() => undefined} />);

    expect(markup).toContain('role="button"');
    expect(markup).toContain('tabindex="0"');
  });

  it("uses the later lymph background beneath a soft white haze", () => {
    const markup = renderToStaticMarkup(<VaccineNarrationScene onComplete={() => undefined} />);
    const narrationRule = styles.match(/\.immune-narration-scene\s*{([^}]*)}/s)?.[1] ?? "";
    const hazeRule = styles.match(/\.immune-narration-scene::before\s*{([^}]*)}/s)?.[1] ?? "";

    expect(markup).toContain(level3Assets.background);
    expect(narrationRule).toContain("background-size: cover");
    expect(hazeRule).toContain("background: rgba(255,255,255,.35)");
    expect(hazeRule).toContain("backdrop-filter: blur(3px)");
  });
});
