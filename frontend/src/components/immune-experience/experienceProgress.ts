export const EXPERIENCE_PROGRESS_KEY = "virus-diary:experience-progress";

export type ExperienceProgress = {
  version: 1;
  hasSeenIntro: boolean;
  levelOneCompleted: boolean;
};

const createDefaultProgress = (): ExperienceProgress => ({
  version: 1,
  hasSeenIntro: false,
  levelOneCompleted: false,
});

export function parseExperienceProgress(rawProgress: string | null): ExperienceProgress {
  if (rawProgress === null) {
    return createDefaultProgress();
  }

  try {
    const parsed: unknown = JSON.parse(rawProgress);

    if (typeof parsed !== "object" || parsed === null) {
      return createDefaultProgress();
    }

    const progress = parsed as Record<string, unknown>;

    if (progress.version !== 1) {
      return createDefaultProgress();
    }

    return {
      version: 1,
      hasSeenIntro: typeof progress.hasSeenIntro === "boolean" ? progress.hasSeenIntro : false,
      levelOneCompleted: typeof progress.levelOneCompleted === "boolean" ? progress.levelOneCompleted : false,
    };
  } catch {
    return createDefaultProgress();
  }
}

export function readExperienceProgress(): ExperienceProgress {
  try {
    return parseExperienceProgress(localStorage.getItem(EXPERIENCE_PROGRESS_KEY));
  } catch {
    return createDefaultProgress();
  }
}

export function writeExperienceProgress(progress: ExperienceProgress): boolean {
  try {
    localStorage.setItem(EXPERIENCE_PROGRESS_KEY, JSON.stringify(progress));
    return true;
  } catch {
    return false;
  }
}
