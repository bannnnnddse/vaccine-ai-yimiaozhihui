import { useCallback, useEffect, useRef, useState } from "react";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import {
  MazeGame,
  type MazeCaptureSnapshot,
  type Point as MazePoint,
  type Size as MazeSize,
} from "./MazeGame/MazeGame";
import { useReducedMotion } from "./useReducedMotion";

export const TISSUE_NARRATION_HOLD_DURATION_MS = 30_000;
const TISSUE_NARRATION_TYPING_SPEED_MS = 85;
export const TISSUE_NARRATION_TEXT = "病毒进入组织间隙后，\n首先会被树突状细胞追捕";

/** Public geometry aliases emitted when the in-maze capture animation completes. */
export type Point = MazePoint;
export type Size = MazeSize;
export type ExploreCaptureSnapshot = MazeCaptureSnapshot;

export interface TissueExploreSceneProps {
  onCapture: (snapshot: ExploreCaptureSnapshot) => void;
}

/**
 * The first-level tissue canvas supplies the medical context around the
 * deterministic maze interaction. The callback fires only after the compact
 * in-maze engulf animation has completed.
 */
export function TissueExploreScene({ onCapture }: TissueExploreSceneProps) {
  const prefersReducedMotion = useReducedMotion();
  const [isNarrating, setIsNarrating] = useState(true);
  const [displayedText, setDisplayedText] = useState("");
  const completedRef = useRef(false);

  const finishNarration = useCallback(() => {
    if (completedRef.current) return;

    completedRef.current = true;
    setIsNarrating(false);
  }, []);

  useEffect(() => {
    let holdTimer: number | undefined;
    let typingTimer: number | undefined;

    const startHold = () => {
      holdTimer = window.setTimeout(finishNarration, TISSUE_NARRATION_HOLD_DURATION_MS);
    };

    if (prefersReducedMotion) {
      setDisplayedText(TISSUE_NARRATION_TEXT);
      startHold();
      return () => {
        if (holdTimer !== undefined) window.clearTimeout(holdTimer);
      };
    }

    let characterIndex = 0;
    const typeNextCharacter = () => {
      characterIndex += 1;
      setDisplayedText(TISSUE_NARRATION_TEXT.slice(0, characterIndex));
      if (characterIndex < TISSUE_NARRATION_TEXT.length) {
        typingTimer = window.setTimeout(typeNextCharacter, TISSUE_NARRATION_TYPING_SPEED_MS);
      } else startHold();
    };
    typingTimer = window.setTimeout(typeNextCharacter, TISSUE_NARRATION_TYPING_SPEED_MS);

    return () => {
      if (typingTimer !== undefined) window.clearTimeout(typingTimer);
      if (holdTimer !== undefined) window.clearTimeout(holdTimer);
    };
  }, [finishNarration, prefersReducedMotion]);

  return (
    <section
      className="immune-level-scene immune-tissue-explore-scene"
      aria-label="组织探索互动"
    >
      <div className="immune-explore-stage">
        <img
          className="immune-explore-background"
          src={level3Assets.background}
          alt=""
          aria-hidden="true"
        />
        {isNarrating ? (
          <div
            className="immune-tissue-narration-scene"
            aria-label="组织间隙追捕说明"
            onClick={finishNarration}
            onKeyDown={(event) => {
              if (event.key !== "Enter" && event.key !== " ") return;
              event.preventDefault();
              finishNarration();
            }}
            role="button"
            tabIndex={0}
          >
            <p className="immune-tissue-narration-scene__line" aria-live="polite">
              {displayedText}
              {!prefersReducedMotion && (
                <span className="immune-tissue-narration-scene__cursor" aria-hidden="true">|</span>
              )}
            </p>
          </div>
        ) : (
          <MazeGame onCapture={onCapture} />
        )}
      </div>
    </section>
  );
}
