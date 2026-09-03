import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { immuneAssets } from "../../assets/immune/immuneAssets";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { AntigenPresentationScene } from "./AntigenPresentationScene";

describe("AntigenPresentationScene", () => {
  it("renders the live capture scene with generated action assets", () => {
    const markup = renderToStaticMarkup(<AntigenPresentationScene onEnded={() => undefined} />);

    expect(markup).toContain(level3Assets.background);
    expect(markup).toContain(immuneAssets.antigenVirusStruggleLeftV2);
    expect(markup).toContain(immuneAssets.dendriticSideHolding);
    expect(markup).toContain(immuneAssets.dendriticCaptureArmUpperV2);
    expect(markup).toContain(immuneAssets.dendriticCaptureArmLowerV2);
    expect(markup).toContain("immune-capture__arm--upper");
    expect(markup).toContain("immune-capture__arm--lower");
    expect(markup).toContain("病毒被树突状细胞摄取过程");
    expect(markup).toContain("挣扎！");
    expect(markup).not.toContain("immune-capture__caption");
    expect(markup).not.toContain("病毒挣扎着被拖向细胞！");
    expect(markup).not.toContain("immune-capture__meter");
    expect(markup).not.toContain("最多还能挣扎");
    expect(markup).not.toMatch(/MHC-II|抗原肽|T\s*细胞/);
  });

  it("uses a native keyboard-accessible struggle button and a frame-driven runtime", () => {
    const markup = renderToStaticMarkup(<AntigenPresentationScene onEnded={() => undefined} />);
    const source = readFileSync(fileURLToPath(new URL("./AntigenPresentationScene.tsx", import.meta.url)), "utf8");

    expect(markup).toContain('type="button"');
    expect(markup).toContain("disabled");
    expect(markup).toContain('aria-live="polite"');
    expect(markup).not.toContain("<video");
    expect(source).toContain("requestAnimationFrame");
    expect(source).toContain("cancelAnimationFrame");
    expect(source).toContain("stopPropagation");
    expect(source).not.toContain("PAUSE_AFTER_CAPTURE_FOR_DEVELOPMENT");
  });

  it("keeps visual motion in CSS variables and includes a reduced-motion fallback", () => {
    const styles = readFileSync(fileURLToPath(new URL("../../styles.css", import.meta.url)), "utf8");
    const visualTuningStyles = readFileSync(fileURLToPath(new URL("../../immune-visual-tuning.css", import.meta.url)), "utf8");

    expect(styles).toContain(".immune-capture__struggle");
    expect(styles).toMatch(/\.immune-capture::after\s*{[^}]*background:\s*rgba\(255,255,255,\.65\)[^}]*backdrop-filter:\s*blur\(3px\)/s);
    expect(styles).toContain(".immune-capture__arm--upper");
    expect(styles).toContain("var(--virus-left)");
    expect(visualTuningStyles).toMatch(/--immune-capture-virus-hand-gap-x:\s*[-\d.]+(?:%|px)/);
    expect(visualTuningStyles).toMatch(/--immune-capture-virus-hand-gap-y:\s*[-\d.]+(?:%|px)/);
    expect(styles).toMatch(/\.immune-capture__virus\s*{[^}]*left:\s*calc\(var\(--virus-left\) \+ var\(--immune-capture-virus-hand-gap-x\)\)[^}]*top:\s*calc\(var\(--virus-top\) \+ var\(--immune-capture-virus-hand-gap-y\)\)/s);
    expect(styles).toContain("var(--immune-capture-upper-arm-x)");
    expect(styles).toContain("var(--immune-capture-upper-arm-y)");
    expect(styles).toContain("var(--immune-capture-upper-arm-root-x)");
    expect(styles).toContain("var(--immune-capture-upper-arm-rotate)");
    expect(styles).toMatch(/--immune-capture-lower-arm-y-offset:\s*[-\d.]+%/);
    expect(styles).toMatch(/--immune-capture-lower-arm-rest-y:\s*[-\d.]+%/);
    expect(styles).toMatch(/--immune-capture-lower-arm-struggle-y:\s*[-\d.]+%/);
    expect(styles).toMatch(/--immune-capture-lower-arm-x:\s*[-\d.]+%/);
    expect(styles).toMatch(/--immune-capture-lower-arm-root-x:\s*[-\d.]+%/);
    expect(styles).toMatch(/\.immune-capture__arm--lower\s*\{[^}]*var\(--immune-capture-lower-arm-x\)[^}]*var\(--immune-capture-lower-arm-rest-y\)[^}]*var\(--immune-capture-lower-arm-y-offset\)[^}]*var\(--immune-capture-lower-arm-root-x\)/s);
    expect(styles).toMatch(/\.immune-capture__arm--lower\s*\{[^}]*z-index:\s*5/s);
    expect(styles).toMatch(/\.immune-capture__virus\s*\{[^}]*z-index:\s*4/s);
    expect(styles).toMatch(/\.immune-capture--strained \.immune-capture__arm--lower\s*\{[^}]*var\(--immune-capture-lower-arm-struggle-y\)[^}]*var\(--immune-capture-lower-arm-y-offset\)/s);
    expect(styles).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*immune-capture/s);
  });
});
