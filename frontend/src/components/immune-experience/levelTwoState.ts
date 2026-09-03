export type LevelTwoPhase = "video" | "video-transition" | "quiz" | "correct-feedback" | "incorrect-feedback";
export type LevelTwoAnswer = "A" | "B" | "C";
export type LevelTwoFeedback = "correct" | "incorrect";

export interface LevelTwoState {
  phase: LevelTwoPhase;
  selectedAnswer: LevelTwoAnswer | null;
}

export const CORRECT_FEEDBACK_MS = 1_500;
export const INCORRECT_FEEDBACK_MS = 1_200;
export const VIDEO_TO_QUIZ_TRANSITION_MS = 350;
export const INITIAL_LEVEL_TWO_STATE: LevelTwoState = { phase: "video", selectedAnswer: null };

export type LevelTwoAction =
  | { type: "video-ended" }
  | { type: "video-transition-finished" }
  | { type: "answer"; answer: LevelTwoAnswer }
  | { type: "incorrect-finished" };

export function transitionLevelTwo(state: LevelTwoState, action: LevelTwoAction): LevelTwoState {
  if (action.type === "video-ended") {
    return state.phase === "video" ? { phase: "video-transition", selectedAnswer: null } : state;
  }
  if (action.type === "video-transition-finished") {
    return state.phase === "video-transition" ? { phase: "quiz", selectedAnswer: null } : state;
  }
  if (action.type === "answer") {
    if (state.phase !== "quiz") return state;
    return {
      phase: action.answer === "A" ? "correct-feedback" : "incorrect-feedback",
      selectedAnswer: action.answer,
    };
  }
  return state.phase === "incorrect-feedback"
    ? { phase: "quiz", selectedAnswer: null }
    : state;
}

export function createLevelTwoTransitionRuntime(
  onTransitionFinished: () => void,
  setTimer = (callback: () => void, delay: number) => globalThis.setTimeout(callback, delay),
  clearTimer = (id: number) => globalThis.clearTimeout(id),
) {
  let active: number | null = null;
  return {
    start() {
      if (active !== null) return false;
      active = setTimer(() => {
        active = null;
        onTransitionFinished();
      }, VIDEO_TO_QUIZ_TRANSITION_MS);
      return true;
    },
    cancel() {
      if (active !== null) clearTimer(active);
      active = null;
    },
  };
}

type TimerId = number;
interface RuntimeOptions {
  onCorrectComplete: () => void;
  onIncorrectComplete: () => void;
  setTimer?: (callback: () => void, delay: number) => TimerId;
  clearTimer?: (id: TimerId) => void;
}

export function createLevelTwoFeedbackRuntime({
  onCorrectComplete,
  onIncorrectComplete,
  setTimer = (callback, delay) => window.setTimeout(callback, delay),
  clearTimer = (id) => window.clearTimeout(id),
}: RuntimeOptions) {
  let active: TimerId | null = null;
  let generation = 0;
  const cancel = () => {
    generation += 1;
    if (active !== null) clearTimer(active);
    active = null;
  };
  return {
    start(feedback: LevelTwoFeedback) {
      if (active !== null) return false;
      const ownGeneration = ++generation;
      let firedSynchronously = false;
      const timer = setTimer(() => {
        firedSynchronously = true;
        if (ownGeneration !== generation) return;
        active = null;
        feedback === "correct" ? onCorrectComplete() : onIncorrectComplete();
      }, feedback === "correct" ? CORRECT_FEEDBACK_MS : INCORRECT_FEEDBACK_MS);
      if (!firedSynchronously && ownGeneration === generation) active = timer;
      return true;
    },
    cancel,
  };
}
