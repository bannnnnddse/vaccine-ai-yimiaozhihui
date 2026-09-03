export const GRAB_DURATION_MS = 360;
export const CAPTURE_DURATION_MS = 6_000;
export const MAX_CAPTURE_DURATION_MS = 10_000;
export const SWALLOW_DURATION_MS = 820;
export const COMPLETE_HOLD_MS = 650;

export type AntigenPresentationPhase = "grabbing" | "struggling" | "swallowing" | "complete";

export interface AntigenPresentationState {
  phase: AntigenPresentationPhase;
  captureElapsedMs: number;
  phaseElapsedMs: number;
  progress: number;
  struggle: number;
  shouldExit: boolean;
}

export type AntigenPresentationAction =
  | { type: "frame"; deltaMs: number }
  | { type: "struggle" };

export const INITIAL_ANTIGEN_PRESENTATION_STATE: AntigenPresentationState = {
  phase: "grabbing",
  captureElapsedMs: 0,
  phaseElapsedMs: 0,
  progress: 0,
  struggle: 0,
  shouldExit: false,
};

export function nextStruggleIntensity(current: number): number {
  return Math.min(1, current + 0.28);
}

export function decayStruggleIntensity(current: number, elapsedMs: number): number {
  return Math.max(0, current - elapsedMs / 900);
}

export function captureProgressDelta(elapsedMs: number, struggleIntensity: number): number {
  const interactiveDuration = CAPTURE_DURATION_MS - GRAB_DURATION_MS;
  return (elapsedMs / interactiveDuration) * (1 - Math.min(1, struggleIntensity) * 0.65);
}

function advanceCapture(state: AntigenPresentationState, deltaMs: number): AntigenPresentationState {
  const captureElapsedMs = Math.min(MAX_CAPTURE_DURATION_MS, state.captureElapsedMs + deltaMs);
  const struggle = decayStruggleIntensity(state.struggle, deltaMs);
  const averageStruggle = (state.struggle + struggle) / 2;
  const interactiveDelta = state.phase === "grabbing"
    ? Math.max(0, captureElapsedMs - GRAB_DURATION_MS)
    : deltaMs;
  const progress = Math.min(1, state.progress + captureProgressDelta(interactiveDelta, averageStruggle));

  if (progress >= 1 || captureElapsedMs >= MAX_CAPTURE_DURATION_MS) {
    return {
      ...state,
      phase: "swallowing",
      captureElapsedMs,
      phaseElapsedMs: 0,
      progress: 1,
      struggle: 0,
    };
  }

  return {
    ...state,
    phase: captureElapsedMs >= GRAB_DURATION_MS ? "struggling" : "grabbing",
    captureElapsedMs,
    phaseElapsedMs: captureElapsedMs >= GRAB_DURATION_MS ? captureElapsedMs - GRAB_DURATION_MS : captureElapsedMs,
    progress,
    struggle,
  };
}

export function transitionAntigenPresentation(
  state: AntigenPresentationState,
  action: AntigenPresentationAction,
): AntigenPresentationState {
  if (action.type === "struggle") {
    return state.phase === "struggling"
      ? { ...state, struggle: nextStruggleIntensity(state.struggle) }
      : state;
  }

  const deltaMs = Math.max(0, action.deltaMs);
  if (deltaMs === 0 || state.shouldExit) return state;

  if (state.phase === "grabbing" || state.phase === "struggling") {
    return advanceCapture(state, deltaMs);
  }

  if (state.phase === "swallowing") {
    const phaseElapsedMs = state.phaseElapsedMs + deltaMs;
    if (phaseElapsedMs >= SWALLOW_DURATION_MS) {
      const completeElapsedMs = phaseElapsedMs - SWALLOW_DURATION_MS;
      return {
        ...state,
        phase: "complete",
        phaseElapsedMs: completeElapsedMs,
        progress: 1,
        struggle: 0,
        shouldExit: completeElapsedMs >= COMPLETE_HOLD_MS,
      };
    }
    return { ...state, phaseElapsedMs };
  }

  const phaseElapsedMs = state.phaseElapsedMs + deltaMs;
  return {
    ...state,
    phaseElapsedMs,
    shouldExit: phaseElapsedMs >= COMPLETE_HOLD_MS,
  };
}
