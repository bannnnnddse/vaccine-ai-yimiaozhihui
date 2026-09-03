import { useCallback, useEffect, useRef, useState } from "react";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { useReducedMotion } from "./useReducedMotion";

const NARRATION_LINES = [
  "你是减毒活疫苗中的病毒颗粒",
  "接下来你将被注射进人类体内",
] as const;

const TYPING_SPEED_MS = 85;
export const HOLD_DURATION_MS = 30_000;

export interface VaccineNarrationSceneProps {
  onComplete: () => void;
}

/** Two-part typewritten prelude. A click only advances while the completed line is being held. */
export function VaccineNarrationScene({ onComplete }: VaccineNarrationSceneProps) {
  const prefersReducedMotion = useReducedMotion();
  const [lineIndex, setLineIndex] = useState(0);
  const [displayedText, setDisplayedText] = useState("");
  const [isWaiting, setIsWaiting] = useState(false);
  const completedRef = useRef(false);

  const advance = useCallback(() => {
    if (!isWaiting) return;

    if (lineIndex < NARRATION_LINES.length - 1) {
      setLineIndex((current) => current + 1);
      return;
    }

    if (completedRef.current) return;
    completedRef.current = true;
    onComplete();
  }, [isWaiting, lineIndex, onComplete]);

  useEffect(() => {
    const line = NARRATION_LINES[lineIndex];
    let timer: number | undefined;
    let holdTimer: number | undefined;
    let characterIndex = 0;
    setDisplayedText(prefersReducedMotion ? line : "");
    setIsWaiting(prefersReducedMotion);

    const startHold = () => {
      setIsWaiting(true);
      holdTimer = window.setTimeout(() => {
        if (lineIndex < NARRATION_LINES.length - 1) setLineIndex((current) => current + 1);
        else if (!completedRef.current) {
          completedRef.current = true;
          onComplete();
        }
      }, HOLD_DURATION_MS);
    };

    if (prefersReducedMotion) {
      startHold();
    } else {
      const typeNextCharacter = () => {
        characterIndex += 1;
        setDisplayedText(line.slice(0, characterIndex));
        if (characterIndex < line.length) timer = window.setTimeout(typeNextCharacter, TYPING_SPEED_MS);
        else startHold();
      };
      timer = window.setTimeout(typeNextCharacter, TYPING_SPEED_MS);
    }

    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      if (holdTimer !== undefined) window.clearTimeout(holdTimer);
    };
  }, [lineIndex, onComplete, prefersReducedMotion]);

  return (
    <section
      className="immune-level-scene immune-narration-scene"
      aria-label="疫苗注射前导叙事"
      data-waiting={isWaiting}
      style={{ backgroundImage: `url(${level3Assets.background})` }}
      onClick={advance}
      onKeyDown={(event) => {
        if (!isWaiting || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        advance();
      }}
      role="button"
      tabIndex={0}
    >
      <p className="immune-narration-scene__line" aria-live="polite">
        {displayedText}
        {!prefersReducedMotion && <span className="immune-narration-scene__cursor" aria-hidden="true">|</span>}
      </p>
    </section>
  );
}
