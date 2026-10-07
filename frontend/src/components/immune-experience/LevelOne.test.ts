// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import {
  completeLevelOneCapture,
  mergeExperienceProgress,
} from "./LevelOne";

describe("mergeExperienceProgress", () => {
  it("updates one flag without discarding the current version or other flag", () => {
    const current = { version: 1, hasSeenIntro: false, levelOneCompleted: true } as const;

    expect(mergeExperienceProgress(current, { hasSeenIntro: true })).toEqual({
      version: 1,
      hasSeenIntro: true,
      levelOneCompleted: true,
    });
  });

  it("marks level one complete without discarding intro progress", () => {
    const current = { version: 1, hasSeenIntro: true, levelOneCompleted: false } as const;
    expect(mergeExperienceProgress(current, { levelOneCompleted: true })).toEqual({
      version: 1,
      hasSeenIntro: true,
      levelOneCompleted: true,
    });
  });
});

describe("capture scene handoff", () => {
  it("does not mount the legacy large capture scene after the maze capture", () => {
    const source = readFileSync(new URL("./LevelOne.tsx", import.meta.url), "utf8");

    expect(source).not.toContain("CaptureScene");
    expect(source).not.toContain('case "capture"');
    expect(source).toContain("onCapture={finishCapture}");
  });
});

describe("LevelOne capture handoff", () => {
  it("persists completion and enters level two immediately after capture", () => {
    const persist = vi.fn();
    const onStartLevelTwo = vi.fn();
    const progress = { version: 1, hasSeenIntro: true, levelOneCompleted: false } as const;

    completeLevelOneCapture(progress, persist, onStartLevelTwo);

    expect(persist).toHaveBeenCalledExactlyOnceWith({
      version: 1,
      hasSeenIntro: true,
      levelOneCompleted: true,
    });
    expect(onStartLevelTwo).toHaveBeenCalledOnce();
  });

  it("contains no explanation scene between capture and level two", () => {
    const source = readFileSync(new URL("./LevelOne.tsx", import.meta.url), "utf8");

    expect(source).not.toContain("ScienceCard");
    expect(source).not.toContain('case "explanation"');
    expect(source).toContain("onCapture={finishCapture}");
  });
});
