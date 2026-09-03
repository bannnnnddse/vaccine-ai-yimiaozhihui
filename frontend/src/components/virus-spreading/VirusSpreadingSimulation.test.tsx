import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  DISEASE_PRESETS,
  CoverageAdjustmentDialog,
  SPREAD_INTRO_ENTER_DURATION_MS,
  SPREAD_INTRO_EXIT_DURATION_MS,
  SPREAD_INTRO_HOLD_DURATION_MS,
  SPREAD_INTRO_LINES,
  VirusSpreadingSimulation,
} from "./VirusSpreadingSimulation";

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

describe("VirusSpreadingSimulation disease presets", () => {
  it("opens with the requested four-part animated introduction", () => {
    const markup = renderToStaticMarkup(<VirusSpreadingSimulation onClose={() => undefined} />);

    expect(SPREAD_INTRO_LINES).toEqual([
      "当疫苗接种率变化时，疾病的传播会发生怎样的变化?",
      "我们预设了新冠，百日咳，甲流，乙流，手足口病五种疾病",
      "模拟中，不同颜色的小球代表不同状态的个体。",
      "我们先来预选一种疾病，开始模拟吧！",
    ]);
    expect(SPREAD_INTRO_ENTER_DURATION_MS).toBe(760);
    expect(SPREAD_INTRO_EXIT_DURATION_MS).toBe(420);
    expect(SPREAD_INTRO_HOLD_DURATION_MS).toBe(30_000);
    expect(markup).toContain('aria-label="疫苗防线玩法介绍"');
    expect(markup).not.toContain("传播对照实验 · 使用说明");
    expect(markup).not.toContain("点击屏幕任意位置继续");
    expect(markup).not.toContain("spread-disease-grid");
  });

  it("keeps all five preset descriptions available for the configuration screen", () => {
    expect(DISEASE_PRESETS).toHaveLength(5);
    expect(DISEASE_PRESETS[0].summary).toContain("疫苗可降低重症和死亡风险");
  });

  it("reveals descriptions on hover, keyboard focus, or selection", () => {
    expect(styles).toMatch(/\.spread-disease-card p\s*{[^}]*opacity:\s*0[^}]*pointer-events:\s*none/s);
    expect(styles).toMatch(/\.spread-disease-card:hover p,\s*\.spread-disease-card:focus-visible p,\s*\.spread-disease-card\[aria-pressed="true"\] p\s*{[^}]*opacity:\s*1/s);
  });

  it("places the introduction directly on the home background without a card shell", () => {
    expect(styles).toMatch(/\.spread-intro-page\s*{[^}]*radial-gradient\(circle at 14% 20%[^}]*linear-gradient\(135deg,\s*#eef9ff 0%,\s*#e7f4fc 54%,\s*#edf5ff 100%\)/s);
    expect(styles).toMatch(/\.spread-intro\s*{[^}]*width:\s*min\(1320px,\s*calc\(100vw - 120px\)\)[^}]*border:\s*0[^}]*background:\s*transparent[^}]*box-shadow:\s*none/s);
  });

  it("drops each caption from the top and fades it out", () => {
    expect(styles).toMatch(/\.spread-intro > p\[data-phase="entering"\]\s*{[^}]*spread-intro-drop/s);
    expect(styles).toMatch(/@keyframes spread-intro-drop\s*{[\s\S]*?translateY\(-70vh\)[\s\S]*?opacity:\s*0[\s\S]*?72%[\s\S]*?translateY\(20px\)[\s\S]*?100%[\s\S]*?translateY\(0\)/);
    expect(styles).toMatch(/\.spread-intro > p\[data-phase="exiting"\]\s*{[^}]*spread-intro-fade/s);
    expect(styles).toMatch(/@keyframes spread-intro-fade\s*{[\s\S]*?opacity:\s*1[\s\S]*?opacity:\s*0/);
  });

  it("aligns both scenario subtitles with their titles at two-thirds scale", () => {
    expect(styles).toMatch(/\.spread-scenario\s*{[^}]*--spread-scenario-title-size:\s*clamp\(19px,\s*2vw,\s*26px\)[^}]*--spread-scenario-subtitle-size:\s*clamp\(12\.67px,\s*1\.333vw,\s*17\.33px\)/s);
    expect(styles).toMatch(/\.spread-scenario__header > div\s*{[^}]*display:\s*flex[^}]*align-items:\s*baseline/s);
    expect(styles).toMatch(/\.spread-scenario__header p\s*{[^}]*margin:\s*0[^}]*font-size:\s*var\(--spread-scenario-subtitle-size\)/s);
  });

  it("provides an accessible vaccination coverage adjustment dialog", () => {
    const markup = renderToStaticMarkup(<CoverageAdjustmentDialog value={67} onChange={() => undefined} onClose={() => undefined} onRestart={() => undefined} />);

    expect(markup).toContain('role="dialog"');
    expect(markup).toContain('aria-modal="true"');
    expect(markup).toContain('type="range"');
    expect(markup).toContain('min="0"');
    expect(markup).toContain('max="100"');
    expect(markup).toContain('value="67"');
    expect(markup).toContain("67%");
    expect(markup).toContain("重新开始");
  });

  it("styles the adjustment trigger and restart action as black buttons with white text", () => {
    expect(styles).toMatch(/\.spread-run-page__actions > button:not\(\.spread-run-page__secondary-action\)\s*{[^}]*color:\s*#fff[^}]*background:\s*#111/s);
    expect(styles).toMatch(/\.spread-coverage-dialog footer button\s*{[^}]*color:\s*#fff[^}]*background:\s*#111/s);
  });
});
