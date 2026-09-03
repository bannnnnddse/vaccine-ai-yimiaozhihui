import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { LevelIntroScene } from "./LevelIntroScene";

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

describe("LevelIntroScene", () => {
  it("renders the introduction without the removed task list, character image, or duplicate medical note", () => {
    const markup = renderToStaticMarkup(<LevelIntroScene onStart={() => undefined} />);

    expect(markup).not.toContain("<img");
    expect(markup).not.toContain("仅供科普参考");
    expect(markup).toContain("一次疫苗接种后，身体里发生了什么？");
    expect(markup).not.toContain('aria-label="本关任务"');
    expect(markup).not.toContain("进入接种现场");
    expect(markup).not.toContain("探索组织环境");
    expect(markup).not.toContain("见证抗原被捕获");
    expect(markup).not.toContain("病毒日记");
    expect(markup).not.toContain("病毒日记 · 第一关");
    expect(markup).not.toContain("跟随一枚疫苗抗原");
    expect(markup).toContain(">开始</button>");
    expect(markup).not.toContain("开始第一关");
  });

  it("centers the introduction and gives its button modal-like corners", () => {
    expect(styles).toMatch(
      /\.immune-level-intro\s*{[^}]*height:\s*100%[^}]*min-height:\s*0[^}]*place-items:\s*center/s,
    );
    expect(styles).toMatch(
      /\.immune-level-copy\s*{[^}]*max-width:[^;}]+;[^}]*text-align:\s*center/s,
    );
    expect(styles).toMatch(
      /\.immune-level-copy\s+button\s*{[^}]*min-height:\s*44px[^}]*border-radius:\s*(?:2[2-6]px|var\(--radius-xl\))/s,
    );
    expect(styles).toMatch(/\.immune-level-copy\s+button:focus-visible\s*{/);
  });

  it("uses the lymph background beneath a 65 percent white haze", () => {
    const markup = renderToStaticMarkup(<LevelIntroScene onStart={() => undefined} />);
    const introRule = styles.match(/\.immune-level-intro\s*{([^}]*)}/s)?.[1] ?? "";
    const hazeRule = styles.match(/\.immune-level-intro::before\s*{([^}]*)}/s)?.[1] ?? "";

    expect(markup).toContain(level3Assets.background);
    expect(introRule).toContain("background-size: cover");
    expect(hazeRule).toContain("background: rgba(255,255,255,.65)");
    expect(hazeRule).toContain("backdrop-filter: blur(3px)");
  });

  it("exposes the start button position and size as documented CSS variables", () => {
    const introRule = styles.match(/\.immune-level-intro\s*{([^}]*)}/s)?.[1] ?? "";
    const buttonRule = styles.match(/\.immune-level-intro \.immune-level-copy button\s*{([^}]*)}/s)?.[1] ?? "";

    expect(introRule).toContain("--immune-start-button-x: 0px");
    expect(introRule).toContain("--immune-start-button-y: 80px");
    expect(introRule).toContain("--immune-start-button-width: 440px");
    expect(introRule).toContain("--immune-start-button-height: 60px");
    expect(buttonRule).toContain("left: var(--immune-start-button-x)");
    expect(buttonRule).toContain("top: var(--immune-start-button-y)");
    expect(buttonRule).toContain("width: min(var(--immune-start-button-width), 100%)");
    expect(buttonRule).toContain("height: var(--immune-start-button-height)");
  });

  it("compacts every content group at 520px-high viewports without shrinking the button", () => {
    const mediaStart = styles.indexOf("@media (max-height: 520px)");
    const nextMediaStart = styles.indexOf("@media", mediaStart + 1);
    const lowHeightStyles = styles.slice(
      mediaStart,
      nextMediaStart === -1 ? styles.length : nextMediaStart,
    );

    expect(mediaStart).toBeGreaterThanOrEqual(0);
    expect(lowHeightStyles).toMatch(/\.immune-level-intro\s*{[^}]*padding:\s*(?:8|9|10|11|12)px/s);
    expect(lowHeightStyles).toMatch(/\.immune-level-copy\s*{[^}]*gap:\s*(?:4|5|6)px/s);
    expect(lowHeightStyles).toMatch(/\.immune-level-copy h2\s*{[^}]*font-size:[^;}]+;[^}]*line-height:/s);
    expect(lowHeightStyles).toMatch(/\.immune-level-copy button\s*{[^}]*min-height:\s*44px[^}]*border-radius:\s*24px/s);
  });
});
