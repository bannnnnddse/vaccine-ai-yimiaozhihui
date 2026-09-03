import { useEffect, useReducer, useRef } from "react";
import { AntigenPresentationQuiz } from "./AntigenPresentationQuiz";
import { LevelTwoVideoScene } from "./LevelTwoVideoScene";
import {
  INITIAL_LEVEL_TWO_STATE,
  createLevelTwoFeedbackRuntime,
  createLevelTwoTransitionRuntime,
  transitionLevelTwo,
  type LevelTwoAnswer,
} from "./levelTwoState";

export interface LevelTwoProps {
  onComplete: () => void;
}

export function LevelTwo({ onComplete }: LevelTwoProps) {
  const [state, dispatch] = useReducer(transitionLevelTwo, INITIAL_LEVEL_TWO_STATE);
  const stateRef = useRef(state);
  stateRef.current = state;
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;
  const runtimeRef = useRef<ReturnType<typeof createLevelTwoFeedbackRuntime> | null>(null);
  const transitionRuntimeRef = useRef<ReturnType<typeof createLevelTwoTransitionRuntime> | null>(null);

  if (!runtimeRef.current) {
    runtimeRef.current = createLevelTwoFeedbackRuntime({
      onCorrectComplete: () => onCompleteRef.current(),
      onIncorrectComplete: () => dispatch({ type: "incorrect-finished" }),
    });
  }

  if (!transitionRuntimeRef.current) {
    transitionRuntimeRef.current = createLevelTwoTransitionRuntime(
      () => dispatch({ type: "video-transition-finished" }),
    );
  }

  useEffect(() => {
    return () => {
      runtimeRef.current?.cancel();
      transitionRuntimeRef.current?.cancel();
    };
  }, []);

  useEffect(() => {
    if (state.phase !== "video-transition") return;
    transitionRuntimeRef.current?.start();
    return () => transitionRuntimeRef.current?.cancel();
  }, [state.phase]);

  const handleAnswer = (answer: LevelTwoAnswer) => {
    if (stateRef.current.phase !== "quiz") return;
    dispatch({ type: "answer", answer });
    runtimeRef.current?.start(answer === "A" ? "correct" : "incorrect");
  };

  useEffect(() => {
    if (typeof window.addEventListener !== "function") return;
    const advance = () => {
      if (stateRef.current.phase === "video") dispatch({ type: "video-ended" });
      else if (stateRef.current.phase === "video-transition") dispatch({ type: "video-transition-finished" });
      else onCompleteRef.current();
    };
    window.addEventListener("immune-experience:developer-advance", advance);
    return () => window.removeEventListener("immune-experience:developer-advance", advance);
  }, []);

  if (state.phase === "video" || state.phase === "video-transition") {
    return (
      <LevelTwoVideoScene
        transitioning={state.phase === "video-transition"}
        onEnded={() => dispatch({ type: "video-ended" })}
      />
    );
  }

  return (
    <AntigenPresentationQuiz
      feedback={state.phase === "correct-feedback" ? "correct" : state.phase === "incorrect-feedback" ? "incorrect" : null}
      selectedAnswer={state.selectedAnswer}
      onAnswer={handleAnswer}
    />
  );
}
