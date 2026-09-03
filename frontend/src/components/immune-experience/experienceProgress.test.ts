import { afterEach, describe, expect, it, vi } from "vitest";
import {
  EXPERIENCE_PROGRESS_KEY,
  parseExperienceProgress,
  readExperienceProgress,
  writeExperienceProgress,
} from "./experienceProgress";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseExperienceProgress", () => {
  it("uses the stable experience progress storage key", () => {
    expect(EXPERIENCE_PROGRESS_KEY).toBe("virus-diary:experience-progress");
  });

  it("returns defaults for missing or damaged data", () => {
    expect(parseExperienceProgress(null)).toEqual({ version: 1, hasSeenIntro: false, levelOneCompleted: false });
    expect(parseExperienceProgress("{")).toEqual({ version: 1, hasSeenIntro: false, levelOneCompleted: false });
  });

  it("accepts only boolean progress fields", () => {
    expect(parseExperienceProgress('{"version":1,"hasSeenIntro":"yes","levelOneCompleted":1}'))
      .toEqual({ version: 1, hasSeenIntro: false, levelOneCompleted: false });
  });

  it("preserves valid progress and ignores unknown fields", () => {
    expect(parseExperienceProgress('{"version":1,"hasSeenIntro":true,"levelOneCompleted":true,"future":"ok"}'))
      .toEqual({ version: 1, hasSeenIntro: true, levelOneCompleted: true });
  });

  it("rejects missing, malformed, or future progress versions", () => {
    const defaults = { version: 1, hasSeenIntro: false, levelOneCompleted: false };

    expect(parseExperienceProgress('{"hasSeenIntro":true,"levelOneCompleted":true}')).toEqual(defaults);
    expect(parseExperienceProgress('{"version":"1","hasSeenIntro":true,"levelOneCompleted":true}')).toEqual(defaults);
    expect(parseExperienceProgress('{"version":2,"hasSeenIntro":true,"levelOneCompleted":true}')).toEqual(defaults);
  });

  it("reads and writes progress through local storage", () => {
    const storedProgress = '{"version":1,"hasSeenIntro":true,"levelOneCompleted":false}';
    const getItem = vi.fn(() => storedProgress);
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { getItem, setItem });

    expect(readExperienceProgress()).toEqual({ version: 1, hasSeenIntro: true, levelOneCompleted: false });
    expect(getItem).toHaveBeenCalledWith(EXPERIENCE_PROGRESS_KEY);

    const progress = { version: 1, hasSeenIntro: true, levelOneCompleted: true } as const;
    expect(writeExperienceProgress(progress)).toBe(true);
    expect(setItem).toHaveBeenCalledWith(EXPERIENCE_PROGRESS_KEY, JSON.stringify(progress));
  });

  it("does not interrupt the experience when local storage throws", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("quota exceeded"); },
    });

    expect(readExperienceProgress()).toEqual({ version: 1, hasSeenIntro: false, levelOneCompleted: false });
    expect(writeExperienceProgress({ version: 1, hasSeenIntro: false, levelOneCompleted: false })).toBe(false);
  });
});
