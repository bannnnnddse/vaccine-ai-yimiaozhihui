import { useEffect, useRef, useState } from "react";
import {
  readExperienceProgress,
  writeExperienceProgress,
  type ExperienceProgress,
} from "./experienceProgress";
import { LevelIntroScene } from "./LevelIntroScene";
import { InjectionScene } from "./InjectionScene";
import { VaccineNarrationScene } from "./VaccineNarrationScene";
import { TissueExploreScene } from "./TissueExploreScene";

export type LevelOneScene = "intro" | "narration" | "injection" | "explore";

export interface LevelOneProps {
  onSceneChange?: (scene: LevelOneScene) => void;
  onStartLevelTwo?: () => void;
}

type ExperienceProgressUpdate = Partial<Pick<ExperienceProgress, "hasSeenIntro" | "levelOneCompleted">>;

export function mergeExperienceProgress(
  progress: ExperienceProgress,
  update: ExperienceProgressUpdate,
): ExperienceProgress {
  return { ...progress, ...update };
}

export function completeLevelOneCapture(
  progress: ExperienceProgress,
  persist: (nextProgress: ExperienceProgress) => void,
  onStartLevelTwo?: () => void,
): void {
  persist(mergeExperienceProgress(progress, { levelOneCompleted: true }));
  onStartLevelTwo?.();
}

export function LevelOne({ onSceneChange, onStartLevelTwo }: LevelOneProps) {
  const [scene, setScene] = useState<LevelOneScene>("intro");
  const onSceneChangeRef = useRef(onSceneChange);
  const captureCompletedRef = useRef(false);

  useEffect(() => {
    onSceneChangeRef.current = onSceneChange;
  }, [onSceneChange]);

  useEffect(() => {
    onSceneChangeRef.current?.(scene);
  }, [scene]);

  const startLevel = () => {
    const progress = readExperienceProgress();
    writeExperienceProgress(mergeExperienceProgress(progress, { hasSeenIntro: true }));
    setScene("narration");
  };

  const finishCapture = () => {
    if (captureCompletedRef.current) return;
    captureCompletedRef.current = true;
    completeLevelOneCapture(readExperienceProgress(), writeExperienceProgress, onStartLevelTwo);
  };

  useEffect(() => {
    if (typeof window.addEventListener !== "function") return;
    const advance = () => {
      if (scene === "intro") startLevel();
      else if (scene === "narration") setScene("injection");
      else if (scene === "injection") setScene("explore");
      else finishCapture();
    };
    window.addEventListener("immune-experience:developer-advance", advance);
    return () => window.removeEventListener("immune-experience:developer-advance", advance);
  }, [scene]);

  switch (scene) {
    case "intro":
      return <LevelIntroScene onStart={startLevel} />;
    case "narration":
      return <VaccineNarrationScene onComplete={() => setScene("injection")} />;
    case "injection":
      return <InjectionScene onComplete={() => setScene("explore")} />;
    case "explore":
      return <TissueExploreScene onCapture={finishCapture} />;
  }
}
