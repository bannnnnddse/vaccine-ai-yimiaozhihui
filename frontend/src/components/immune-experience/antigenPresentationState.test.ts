import { describe, expect, it } from "vitest";
import {
  CAPTURE_DURATION_MS,
  COMPLETE_HOLD_MS,
  GRAB_DURATION_MS,
  INITIAL_ANTIGEN_PRESENTATION_STATE,
  MAX_CAPTURE_DURATION_MS,
  SWALLOW_DURATION_MS,
  captureProgressDelta,
  decayStruggleIntensity,
  nextStruggleIntensity,
  transitionAntigenPresentation,
  type AntigenPresentationState,
} from "./antigenPresentationState";

function frame(state: AntigenPresentationState, deltaMs: number): AntigenPresentationState {
  return transitionAntigenPresentation(state, { type: "frame", deltaMs });
}

describe("antigen presentation state", () => {
  it("runs grab, six-second capture, swallow, hold, and exit in order", () => {
    const struggling = frame(INITIAL_ANTIGEN_PRESENTATION_STATE, GRAB_DURATION_MS);
    const swallowing = frame(struggling, CAPTURE_DURATION_MS - GRAB_DURATION_MS);
    const complete = frame(swallowing, SWALLOW_DURATION_MS);
    const exited = frame(complete, COMPLETE_HOLD_MS);

    expect(struggling.phase).toBe("struggling");
    expect(swallowing).toMatchObject({ phase: "swallowing", progress: 1 });
    expect(complete).toMatchObject({ phase: "complete", shouldExit: false });
    expect(exited.shouldExit).toBe(true);
  });

  it("lets repeated struggle pulses delay capture without breaking the ten-second cap", () => {
    let state = frame(INITIAL_ANTIGEN_PRESENTATION_STATE, GRAB_DURATION_MS);
    while (state.captureElapsedMs < CAPTURE_DURATION_MS) {
      state = transitionAntigenPresentation(state, { type: "struggle" });
      state = frame(state, 200);
    }

    expect(state.phase).toBe("struggling");
    expect(state.progress).toBeLessThan(1);

    while (state.phase === "struggling") {
      state = transitionAntigenPresentation(state, { type: "struggle" });
      state = frame(state, 200);
    }

    expect(state.phase).toBe("swallowing");
    expect(state.captureElapsedMs).toBe(MAX_CAPTURE_DURATION_MS);
  });

  it("stacks and decays struggle intensity only during the interactive phase", () => {
    expect(transitionAntigenPresentation(INITIAL_ANTIGEN_PRESENTATION_STATE, { type: "struggle" }))
      .toBe(INITIAL_ANTIGEN_PRESENTATION_STATE);
    expect(nextStruggleIntensity(0)).toBeCloseTo(0.28);
    expect(nextStruggleIntensity(0.9)).toBe(1);
    expect(decayStruggleIntensity(1, 900)).toBe(0);
    expect(captureProgressDelta(CAPTURE_DURATION_MS - GRAB_DURATION_MS, 0)).toBeCloseTo(1);
    expect(captureProgressDelta(CAPTURE_DURATION_MS - GRAB_DURATION_MS, 1)).toBeLessThan(1);
  });

  it("ignores zero and negative frame deltas after completion", () => {
    expect(frame(INITIAL_ANTIGEN_PRESENTATION_STATE, 0)).toBe(INITIAL_ANTIGEN_PRESENTATION_STATE);
    expect(frame(INITIAL_ANTIGEN_PRESENTATION_STATE, -50)).toBe(INITIAL_ANTIGEN_PRESENTATION_STATE);

    const exited = { ...INITIAL_ANTIGEN_PRESENTATION_STATE, phase: "complete" as const, shouldExit: true };
    expect(frame(exited, 500)).toBe(exited);
  });
});
