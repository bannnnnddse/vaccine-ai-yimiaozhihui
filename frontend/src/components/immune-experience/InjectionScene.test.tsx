import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { immuneAssets } from "../../assets/immune/immuneAssets";
import {
  getInjectionDuration,
  InjectionScene,
  INJECTION_DURATION_MS,
  REDUCED_MOTION_DURATION_MS,
  scheduleInjectionCompletion,
} from "./InjectionScene";

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

describe("InjectionScene", () => {
  it("uses the four-second duration unless reduced motion is requested", () => {
    expect(INJECTION_DURATION_MS).toBe(4_000);
    expect(REDUCED_MOTION_DURATION_MS).toBe(50);
    expect(getInjectionDuration(false)).toBe(4_000);
    expect(getInjectionDuration(true)).toBe(50);
  });

  it("renders the approved injection assets and an accessible completion status", () => {
    const markup = renderToStaticMarkup(<InjectionScene onComplete={() => undefined} />);

    expect(markup).toContain(immuneAssets.skinLayer);
    expect(markup).toContain(immuneAssets.needle);
    expect(markup).toContain(immuneAssets.injectionVirus);
    expect(markup).not.toContain(immuneAssets.virusNeutral);
    expect(markup).toContain('role="status"');
    expect(markup).not.toContain("immune-injection-skip");
  });

  it("exposes documented needle placement variables and reuses them in every final state", () => {
    const configurableTransform = String.raw`translate3d\(\s*-50%\s*,\s*-50%\s*,\s*0\s*\)\s*rotate\(\s*var\(\s*--immune-needle-rotation\s*\)\s*\)`;

    expect(styles).toMatch(
      /\.immune-injection-scene\s*{[^}]*--immune-needle-start-left:\s*[^;]+;[^}]*--immune-needle-start-top:\s*[^;]+;[^}]*--immune-needle-end-left:\s*[^;]+;[^}]*--immune-needle-end-top:\s*[^;]+;[^}]*--immune-needle-rotation:\s*[^;]+;/s,
    );
    expect(styles).toMatch(
      /\.immune-injection-needle\s*{[^}]*left:\s*var\(\s*--immune-needle-start-left\s*\)[^}]*top:\s*var\(\s*--immune-needle-start-top\s*\)/s,
    );
    expect(styles).toMatch(
      new RegExp(String.raw`\.immune-injection-needle\s*{[^}]*transform:\s*${configurableTransform}`),
    );
    expect(styles).toMatch(
      new RegExp(String.raw`@keyframes\s+immune-needle-enter\s*{[\s\S]*?100%\s*{[^}]*left:\s*var\(\s*--immune-needle-end-left\s*\)[^}]*top:\s*var\(\s*--immune-needle-end-top\s*\)[^}]*transform:\s*${configurableTransform}`),
    );

    const reducedMotionStart = styles.indexOf("@media (prefers-reduced-motion: reduce)");
    const reducedMotionStyles = styles.slice(reducedMotionStart);
    expect(reducedMotionStart).toBeGreaterThanOrEqual(0);
    expect(reducedMotionStyles).toMatch(
      new RegExp(String.raw`\.immune-injection-needle\s*{[^}]*animation:\s*none\s*!important[^}]*left:\s*var\(\s*--immune-needle-end-left\s*\)[^}]*top:\s*var\(\s*--immune-needle-end-top\s*\)[^}]*transform:\s*${configurableTransform}`),
    );
  });

  it("exposes independently adjustable paths for all four viruses", () => {
    expect(styles).toContain("left 增大向右，top 增大向下");
    expect(styles).toMatch(
      /\.immune-injection-scene\s*{[^}]*--immune-virus-1-start-left:\s*58\.4%[^}]*--immune-virus-1-start-top:\s*45%[^}]*--immune-virus-1-end-left:\s*71\.1%[^}]*--immune-virus-1-end-top:\s*57%[^}]*--immune-virus-4-start-left:\s*56\.4%[^}]*--immune-virus-4-start-top:\s*44%[^}]*--immune-virus-4-end-left:\s*60\.3%[^}]*--immune-virus-4-end-top:\s*48\.6%/s,
    );
    expect(styles).toMatch(
      /\.immune-injection-antigen\s*{[^}]*left:\s*var\(--immune-virus-start-left\)[^}]*top:\s*var\(--immune-virus-start-top\)[^}]*transform:\s*translate3d\(-50%,\s*-50%,\s*0\)\s*scale\(\.4\)/s,
    );
    expect(styles).toMatch(
      /@keyframes\s+immune-antigen-arrive\s*{[^}]*0%\s*{[^}]*left:\s*var\(--immune-virus-start-left\)[^}]*top:\s*var\(--immune-virus-start-top\)[\s\S]*?100%\s*{[^}]*left:\s*var\(--immune-virus-end-left\)[^}]*top:\s*var\(--immune-virus-end-top\)/s,
    );
  });

  it.each([
    [false, 4_000],
    [true, 50],
  ])("schedules the correct completion delay for reduced motion %s", (reducedMotion, expectedDelay) => {
    const setTimer = vi.fn(() => 17);

    scheduleInjectionCompletion({
      delay: getInjectionDuration(reducedMotion),
      onComplete: vi.fn(),
      setTimer,
      clearTimer: vi.fn(),
    });

    expect(setTimer).toHaveBeenCalledOnce();
    expect(setTimer).toHaveBeenCalledWith(expect.any(Function), expectedDelay);
  });

  it("clears its scheduled timer during cleanup", () => {
    const clearTimer = vi.fn();
    const schedule = scheduleInjectionCompletion({
      delay: 4_000,
      onComplete: vi.fn(),
      setTimer: vi.fn(() => 23),
      clearTimer,
    });

    schedule.cancel();

    expect(clearTimer).toHaveBeenCalledOnce();
    expect(clearTimer).toHaveBeenCalledWith(23);
  });

  it("completes once when manual finish races with the scheduled callback", () => {
    const onComplete = vi.fn();
    let scheduledFinish = () => undefined;
    const schedule = scheduleInjectionCompletion({
      delay: 4_000,
      onComplete,
      setTimer: vi.fn((callback) => {
        scheduledFinish = callback;
        return 31;
      }),
      clearTimer: vi.fn(),
    });

    schedule.finish();
    scheduledFinish();

    expect(onComplete).toHaveBeenCalledOnce();
  });
});
