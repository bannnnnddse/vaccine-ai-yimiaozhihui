import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BLINK_DURATION_MS,
  BLINK_COOLDOWN_MS,
  createAvatarGazeRuntime,
  type AvatarGazeState,
} from "./avatarGazeState";

describe("avatar gaze runtime", () => {
  afterEach(() => vi.useRealTimers());

  function createRuntime(blinkCooldown = 1_000_000) {
    vi.useFakeTimers();
    const states: AvatarGazeState[] = [];
    const runtime = createAvatarGazeRuntime({
      onStateChange: (state) => states.push(state),
      getBlinkCooldown: () => blinkCooldown,
    });
    return { runtime, states };
  }

  function expectBlinkRestores() {
    const { runtime, states } = createRuntime();
    runtime.blink();
    expect(runtime.getState()).toEqual({ visualState: "blink" });
    vi.advanceTimersByTime(BLINK_DURATION_MS);
    expect(runtime.getState()).toEqual({ visualState: "rest" });
    expect(states.at(-1)?.visualState).toBe("rest");
    runtime.dispose();
  }

  it("restores normal eyes after a blink", expectBlinkRestores);

  it("blinks automatically after the eight-second cooldown", () => {
    const { runtime } = createRuntime(BLINK_COOLDOWN_MS);
    vi.advanceTimersByTime(BLINK_COOLDOWN_MS);
    expect(runtime.getState().visualState).toBe("blink");
    runtime.dispose();
  });

  it("blinks when the pointer moves", () => {
    const { runtime } = createRuntime();
    runtime.pointerMoved();
    expect(runtime.getState().visualState).toBe("blink");
    vi.advanceTimersByTime(BLINK_DURATION_MS);
    runtime.pointerMoved();
    expect(runtime.getState().visualState).toBe("rest");
    runtime.dispose();
  });

  it("does not emit delayed updates after disposal", () => {
    const { runtime, states } = createRuntime();
    runtime.blink();
    const countAtDispose = states.length;
    runtime.dispose();
    vi.runAllTimers();
    expect(states).toHaveLength(countAtDispose);
  });
});
