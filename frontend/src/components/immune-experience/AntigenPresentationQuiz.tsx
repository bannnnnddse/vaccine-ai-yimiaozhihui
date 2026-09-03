import { useEffect, useRef } from "react";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import type { LevelTwoAnswer, LevelTwoFeedback } from "./levelTwoState";
import { useReducedMotion } from "./useReducedMotion";

const answers: Array<{ id: LevelTwoAnswer; text: string; compact?: boolean }> = [
  { id: "A", text: "为了让T细胞识别", compact: true },
  { id: "B", text: "为了被抗体直接攻击" },
  { id: "C", text: "为了逃避免疫系统" },
];

export interface AntigenPresentationQuizProps {
  feedback: LevelTwoFeedback | null;
  selectedAnswer: LevelTwoAnswer | null;
  onAnswer: (answer: LevelTwoAnswer) => void;
}

export function AntigenPresentationQuiz({
  feedback,
  selectedAnswer,
  onAnswer,
}: AntigenPresentationQuizProps) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  const locked = feedback !== null;
  const message = feedback === "correct"
    ? "正确！T细胞正在赶来"
    : feedback === "incorrect"
      ? "不对哦，再想想..."
      : "";

  return (
    <section
      className={`immune-level-two-quiz${feedback ? ` immune-is-${feedback}` : ""}`}
      aria-labelledby="immune-level-two-question"
      data-reduced-motion={prefersReducedMotion}
    >
      <img
        className="immune-level-two-quiz-background"
        src={level3Assets.background}
        alt=""
        aria-hidden="true"
      />
      <div className="immune-level-two-quiz-content">
        <h2 ref={titleRef} id="immune-level-two-question" tabIndex={-1}>
          树突状细胞展示抗原的目的是？
        </h2>
        <div className="immune-level-two-answer-row">
          {answers.map(({ id, text, compact }) => (
            <button
              key={id}
              type="button"
              className="immune-level-two-answer-card"
              data-selected={selectedAnswer === id}
              disabled={locked}
              onClick={() => onAnswer(id)}
            >
              <span className="immune-level-two-answer-letter">{id}</span>
              <span>{id}.{compact ? "" : " "}{text}</span>
            </button>
          ))}
        </div>
        <p className="immune-level-two-feedback" role="status" aria-live="assertive">
          {message}
        </p>
      </div>
    </section>
  );
}
