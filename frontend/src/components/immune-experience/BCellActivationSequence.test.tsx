import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { BCellActivationSequence } from "./BCellActivationSequence";

describe("BCellActivationSequence", () => {
  it("places the helper T cell in the center before antigen presentation", () => {
    const markup = renderToStaticMarkup(<BCellActivationSequence phase="focus-b-cell" />);

    expect(markup).toContain("data-helper-t-focus");
    expect(markup).not.toContain("data-activation-b-cell");
  });

  it("brings the antigen-presenting cell in to contact the centered helper T cell", () => {
    const markup = renderToStaticMarkup(<BCellActivationSequence phase="t-cell-contact" />);

    expect(markup).toContain("data-helper-t-focus");
    expect(markup).toContain("data-antigen-presenter");
    expect(markup).toContain(level3Assets.helperTCell);
    expect(markup).toContain(level3Assets.antigenPresentingCell);
    expect(markup).not.toContain("data-activation-b-cell");
  });

  it("keeps the helper T cell and antigen presenter together during the contact hold", () => {
    const markup = renderToStaticMarkup(<BCellActivationSequence phase="t-cell-contact-hold" />);

    expect(markup).toContain("data-antigen-presenter");
    expect(markup).toContain("data-helper-t-focus");
  });

  it("keeps both contacting cells visible at the end of the approach animation", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../../styles.css", import.meta.url)),
      "utf8",
    );
    expect(styles).toMatch(
      /@keyframes immune-antigen-presenter-cross\s*{[^}]*0%[^}]*opacity:\s*0[^}]*}[^}]*55%,\s*72%[^}]*opacity:\s*1[^}]*}[^}]*100%[^}]*opacity:\s*1[^}]*}/s,
    );
    expect(styles).toMatch(
      /\.immune-b-cell-activation\.is-t-cell-contact-hold \.immune-b-cell-activation__presenter\s*{[^}]*opacity:\s*1[^}]*animation:\s*none/s,
    );
  });

  it("exposes one shared set of presenter position controls for motion and hold states", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../../styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toMatch(
      /\.immune-b-cell-activation\s*{[^}]*--immune-antigen-presenter-left:\s*[\d.]+%;[^}]*--immune-antigen-presenter-top:\s*[\d.]+%;[^}]*--immune-antigen-presenter-contact-x:\s*-?[\d.]+%;[^}]*--immune-antigen-presenter-contact-y:\s*-?[\d.]+%;/s,
    );
    expect(styles).toMatch(
      /\.immune-b-cell-activation__presenter\s*{[^}]*left:\s*var\(--immune-antigen-presenter-left\)[^}]*top:\s*var\(--immune-antigen-presenter-top\)/s,
    );
    expect(styles.match(/var\(--immune-antigen-presenter-contact-x\)/g)).toHaveLength(3);
    expect(styles.match(/var\(--immune-antigen-presenter-contact-y\)/g)).toHaveLength(4);
  });

  it("moves the helper T cell to the B cell and shows the B-cell response", () => {
    const markup = renderToStaticMarkup(<BCellActivationSequence phase="antigen-presentation" />);

    expect(markup).toContain("data-activation-b-cell");
    expect(markup).toContain("data-helper-t-contact");
    expect(markup).toContain("收到");
    expect(markup).not.toContain("data-antigen-presenter");
  });

  it("turns the helper T cell before it starts moving toward the B cell", () => {
    const markup = renderToStaticMarkup(<BCellActivationSequence phase="antigen-presentation" />);
    const styles = readFileSync(
      fileURLToPath(new URL("../../styles.css", import.meta.url)),
      "utf8",
    );
    const visualTuningStyles = readFileSync(
      fileURLToPath(new URL("../../immune-visual-tuning.css", import.meta.url)),
      "utf8",
    );

    expect(markup).toContain("immune-helper-t-cell__body");
    expect(markup).toContain("immune-helper-t-cell__label");
    expect(markup).toContain(level3Assets.helperTCellLabel);
    expect(markup.match(/class="immune-helper-t-cell__(?:body|label)"/g)).toHaveLength(2);
    expect(styles).toMatch(
      /\.immune-b-cell-activation__helper-to-b\s*{[^}]*animation:\s*immune-helper-to-b\s+1\.5s/s,
    );
    expect(styles).toMatch(
      /\.immune-b-cell-activation__helper-to-b \.immune-helper-t-cell__body\s*{[^}]*animation:\s*immune-helper-turn-to-b\s+300ms/s,
    );
    expect(visualTuningStyles).toMatch(
      /\.immune-b-cell-activation\s*{[^}]*--immune-helper-t-cell-contact-bubble-x:\s*-?[\d.]+px;[^}]*--immune-helper-t-cell-contact-bubble-y:\s*-?[\d.]+px;[^}]*--immune-helper-t-cell-to-b-bubble-x:\s*-?[\d.]+px;[^}]*--immune-helper-t-cell-to-b-bubble-y:\s*-?[\d.]+px;/s,
    );
    expect(styles).toMatch(
      /\.immune-helper-t-cell > \.immune-helper-t-cell__label\s*{[^}]*position:\s*absolute[^}]*left:\s*10\.125%[^}]*top:\s*86\.68%/s,
    );
    expect(styles).toMatch(
      /\.immune-b-cell-activation__helper-focus \.immune-helper-t-cell__label\s*{[^}]*translate3d\(var\(--immune-helper-t-cell-contact-bubble-x\),\s*var\(--immune-helper-t-cell-contact-bubble-y\),\s*0\)/s,
    );
    expect(styles).toMatch(
      /\.immune-b-cell-activation__helper-to-b \.immune-helper-t-cell__label\s*{[^}]*translate3d\(var\(--immune-helper-t-cell-to-b-bubble-x\),\s*var\(--immune-helper-t-cell-to-b-bubble-y\),\s*0\)/s,
    );
    expect(styles).toMatch(
      /@keyframes immune-helper-turn-to-b\s*{\s*from\s*{[^}]*scaleX\(1\)[^}]*}\s*to\s*{[^}]*scaleX\(-1\)/s,
    );
    expect(styles).toMatch(
      /@keyframes immune-helper-to-b\s*{\s*0%,\s*20%\s*{[^}]*translate3d\(15%,\s*-50%,\s*0\)[^}]*}\s*100%/s,
    );
    expect(styles).toMatch(
      /\.immune-b-cell-activation__helper-to-b \.immune-helper-t-cell__body\s*{\s*animation:\s*none;\s*transform:\s*scaleX\(-1\);\s*}/s,
    );
  });

  it("keeps the B cell and helper T cell together during the antigen-presentation hold", () => {
    const markup = renderToStaticMarkup(<BCellActivationSequence phase="antigen-presentation-hold" />);

    expect(markup).toContain("data-activation-b-cell");
    expect(markup).toContain("data-helper-t-contact");
  });

  it("hands the final neutralized state to the differentiation finale", () => {
    const markup = renderToStaticMarkup(<BCellActivationSequence phase="neutralized" />);

    expect(markup.match(/data-neutralization-virus=/g)).toHaveLength(4);
    expect(markup).not.toContain("data-activation-b-cell");
  });
});
