import { describe, expect, it, vi } from "vitest";
import {
  CORRECT_FEEDBACK_MS,
  INCORRECT_FEEDBACK_MS,
  INITIAL_LEVEL_TWO_STATE,
  VIDEO_TO_QUIZ_TRANSITION_MS,
  createLevelTwoFeedbackRuntime,
  createLevelTwoTransitionRuntime,
  transitionLevelTwo,
} from "./levelTwoState";

describe("transitionLevelTwo", () => {
  it("moves from video through an explicit transition before the quiz", () => {
    expect(transitionLevelTwo(INITIAL_LEVEL_TWO_STATE, { type: "video-ended" })).toEqual({
      phase: "video-transition",
      selectedAnswer: null,
    });
    expect(transitionLevelTwo(
      { phase: "video-transition", selectedAnswer: null },
      { type: "video-transition-finished" },
    )).toEqual({ phase: "quiz", selectedAnswer: null });
  });

  it("keeps the ended video mounted for exactly 350ms and clears pending handoff work", () => {
    vi.useFakeTimers();
    const onFinished = vi.fn();
    expect(VIDEO_TO_QUIZ_TRANSITION_MS).toBe(350);
    expect(createLevelTwoTransitionRuntime).toBeTypeOf("function");

    const runtime = createLevelTwoTransitionRuntime(onFinished);
    runtime.start();
    vi.advanceTimersByTime(349);
    expect(onFinished).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onFinished).toHaveBeenCalledOnce();

    const cancelled = createLevelTwoTransitionRuntime(onFinished);
    cancelled.start();
    cancelled.cancel();
    vi.advanceTimersByTime(350);
    expect(onFinished).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });

  it("accepts A as correct and ignores a second answer while locked", () => {
    const quiz = { phase: "quiz", selectedAnswer: null } as const;
    const correct = transitionLevelTwo(quiz, { type: "answer", answer: "A" });
    expect(correct).toEqual({ phase: "correct-feedback", selectedAnswer: "A" });
    expect(transitionLevelTwo(correct, { type: "answer", answer: "B" })).toBe(correct);
  });

  it.each(["B", "C"] as const)("returns %s to quiz after incorrect feedback", (answer) => {
    const quiz = { phase: "quiz", selectedAnswer: null } as const;
    const incorrect = transitionLevelTwo(quiz, { type: "answer", answer });
    expect(incorrect).toEqual({ phase: "incorrect-feedback", selectedAnswer: answer });
    expect(transitionLevelTwo(incorrect, { type: "incorrect-finished" })).toEqual(quiz);
  });
});

describe("createLevelTwoFeedbackRuntime", () => {
  it("locks the exact feedback durations and their correct/incorrect mapping", () => {
    expect(CORRECT_FEEDBACK_MS).toBe(1_500);
    expect(INCORRECT_FEEDBACK_MS).toBe(1_200);
    const delays: number[] = [];
    const runtime = createLevelTwoFeedbackRuntime({
      onCorrectComplete: vi.fn(),
      onIncorrectComplete: vi.fn(),
      setTimer: (_callback, delay) => { delays.push(delay); return delays.length; },
      clearTimer: vi.fn(),
    });

    runtime.start("correct");
    runtime.cancel();
    runtime.start("incorrect");

    expect(delays).toEqual([1_500, 1_200]);
  });
  it("uses exact delays, settles once, and cancels active work", () => {
    const callbacks = new Map<number, () => void>();
    let nextId = 1;
    const clearTimer = vi.fn((id: number) => callbacks.delete(id));
    const onCorrectComplete = vi.fn();
    const onIncorrectComplete = vi.fn();
    const runtime = createLevelTwoFeedbackRuntime({
      onCorrectComplete,
      onIncorrectComplete,
      setTimer: (callback, delay) => {
        expect([CORRECT_FEEDBACK_MS, INCORRECT_FEEDBACK_MS]).toContain(delay);
        const id = nextId++;
        callbacks.set(id, callback);
        return id;
      },
      clearTimer,
    });

    runtime.start("incorrect");
    expect(runtime.start("incorrect")).toBe(false);
    callbacks.get(1)?.();
    expect(onIncorrectComplete).toHaveBeenCalledOnce();

    runtime.start("correct");
    runtime.cancel();
    expect(clearTimer).toHaveBeenCalledWith(2);
    callbacks.get(2)?.();
    expect(onCorrectComplete).not.toHaveBeenCalled();
  });

  it("does not retain a timer that fires synchronously", () => {
    const onIncorrectComplete = vi.fn();
    const runtime = createLevelTwoFeedbackRuntime({
      onCorrectComplete: vi.fn(),
      onIncorrectComplete,
      setTimer: (callback) => { callback(); return 99; },
      clearTimer: vi.fn(),
    });
    expect(runtime.start("incorrect")).toBe(true);
    expect(onIncorrectComplete).toHaveBeenCalledOnce();
    expect(runtime.start("correct")).toBe(true);
  });
});
