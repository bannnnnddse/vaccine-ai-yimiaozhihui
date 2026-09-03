export const BLINK_DURATION_MS = 120;
export const BLINK_COOLDOWN_MS = 8_000;

export type AvatarVisualState = "rest" | "blink";

export interface AvatarGazeState {
  visualState: AvatarVisualState;
}

interface AvatarGazeDependencies {
  onStateChange: (state: AvatarGazeState) => void;
  getBlinkCooldown?: () => number;
}

const initialState: AvatarGazeState = {
  visualState: "rest",
};

export function createAvatarGazeRuntime({
  onStateChange,
  getBlinkCooldown = () => BLINK_COOLDOWN_MS,
}: AvatarGazeDependencies) {
  let state = initialState;
  let disposed = false;
  let coolingDown = false;
  let visualToken = 0;
  let blinkTimer: ReturnType<typeof setTimeout> | null = null;
  const timers = new Set<ReturnType<typeof setTimeout>>();

  const emit = (next: AvatarGazeState) => {
    if (disposed) return;
    state = next;
    onStateChange(next);
  };
  const later = (callback: () => void, delay: number) => {
    const timer = setTimeout(() => {
      timers.delete(timer);
      callback();
    }, delay);
    timers.add(timer);
    return timer;
  };
  const clearNaturalBlink = () => {
    if (blinkTimer !== null) clearTimeout(blinkTimer);
    blinkTimer = null;
  };

  const naturalBlink = () => {
    if (disposed || coolingDown || state.visualState === "blink") return;
    const token = ++visualToken;
    emit({ visualState: "blink" });
    later(() => {
      if (disposed || token !== visualToken) return;
      emit({ visualState: "rest" });
      coolingDown = true;
      scheduleNextBlink();
    }, BLINK_DURATION_MS);
  };

  const scheduleNextBlink = () => {
    clearNaturalBlink();
    if (disposed) return;
    blinkTimer = later(() => {
      blinkTimer = null;
      coolingDown = false;
      naturalBlink();
    }, getBlinkCooldown());
  };

  scheduleNextBlink();

  return {
    pointerMoved: naturalBlink,
    blink: naturalBlink,
    getState: () => state,
    dispose() {
      disposed = true;
      visualToken += 1;
      clearNaturalBlink();
      for (const timer of timers) clearTimeout(timer);
      timers.clear();
    },
  };
}
