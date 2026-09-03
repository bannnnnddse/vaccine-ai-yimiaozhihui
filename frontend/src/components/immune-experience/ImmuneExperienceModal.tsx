import { useCallback, useEffect, useState } from "react";
import { LevelOne, type LevelOneScene } from "./LevelOne";
import { LevelThree } from "./LevelThree";
import { LevelTwo } from "./LevelTwo";

export interface ImmuneExperienceModalProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
  onStartLevelTwo?: () => void;
  onStartLevelThree?: () => void;
}

type SetExperienceStage = (stage: "level-one" | "level-two" | "level-three") => void;

export function startLevelTwoStage(setStage: SetExperienceStage, notify?: () => void): void {
  setStage("level-two");
  notify?.();
}

export function completeLevelTwoStage(setStage: SetExperienceStage): void {
  setStage("level-three");
}

export function ImmuneExperienceModal({
  open,
  embedded = false,
  onClose,
  onStartLevelTwo,
  onStartLevelThree,
}: ImmuneExperienceModalProps) {
  const [experienceStage, setExperienceStage] = useState<"level-one" | "level-two" | "level-three">("level-one");

  const handleSceneChange = useCallback((_nextScene: LevelOneScene) => {}, []);

  const handleStartLevelTwo = useCallback(() => {
    startLevelTwoStage(setExperienceStage, onStartLevelTwo);
  }, [onStartLevelTwo]);

  const handleLevelTwoComplete = useCallback(() => {
    completeLevelTwoStage(setExperienceStage);
  }, []);

  const advanceToNextDeveloperScene = useCallback(() => {
    window.dispatchEvent(new Event("immune-experience:developer-advance"));
  }, []);

  useEffect(() => {
    if (!open || typeof window.addEventListener !== "function") return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "Tab") {
        // 临时开发快捷键：发布前移除，避免覆盖正常的键盘焦点导航。
        event.preventDefault();
        advanceToNextDeveloperScene();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [advanceToNextDeveloperScene, onClose, open]);

  useEffect(() => {
    if (!open) setExperienceStage("level-one");
  }, [open]);

  if (!open) return null;

  return (
    <div className={`immune-modal-backdrop${embedded ? " immune-modal-backdrop--embedded" : ""}`} role={embedded ? undefined : "presentation"}>
      <section
        className={`immune-modal${embedded ? " immune-modal--embedded" : ""}`}
        role={embedded ? "region" : "dialog"}
        aria-modal={embedded ? undefined : true}
        aria-labelledby="immune-experience-title"
        tabIndex={-1}
      >
        <h1 id="immune-experience-title" className="sr-only">病毒日记免疫科普体验</h1>
        <div className="immune-modal-content">
          {experienceStage === "level-one" && (
            <LevelOne onSceneChange={handleSceneChange} onStartLevelTwo={handleStartLevelTwo} />
          )}
          {experienceStage === "level-two" && <LevelTwo onComplete={handleLevelTwoComplete} />}
          {experienceStage === "level-three" && <LevelThree onEnter={onStartLevelThree} />}
        </div>
      </section>
    </div>
  );
}
