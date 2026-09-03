import { DENDRITIC_START, type MazeMap } from "./mazeMap";

/* 追击速度微调入口：单位均为毫秒；每格耗时越大，树突状细胞越慢。 */
export const PURSUIT_START_DELAY_MS = 2000;
export const PURSUIT_DEADLINE_MS = 20_000000;
export const PURSUIT_SPEED_UP_MS = 8_000;
export const DENDRITIC_MILLISECONDS_PER_CELL = 10;
export const DENDRITIC_MILLISECONDS_PER_CELL_AFTER_SPEED_UP =5;

export const getPursuitInterval = (elapsed: number) =>
  elapsed < PURSUIT_SPEED_UP_MS ? 90 : 45;

export function getDendriticMoveDuration(pathLength: number, elapsed: number): number {
  const millisecondsPerCell = elapsed < PURSUIT_SPEED_UP_MS
    ? DENDRITIC_MILLISECONDS_PER_CELL
    : DENDRITIC_MILLISECONDS_PER_CELL_AFTER_SPEED_UP;
  return Math.max(120, (pathLength - 1) * millisecondsPerCell);
}

type TimerId = ReturnType<typeof globalThis.setTimeout>;

export type MazePursuitPhase = "idle" | "waiting" | "chasing" | "finale" | "captured" | "cancelled";

export interface MazePursuitDependencies {
  map: MazeMap;
  getVirusNode(): string;
  takeNextTrailSegment(): readonly string[] | undefined;
  onDendriticMove(nodeId: string, durationMs: number): void;
  onFinaleStart?(): void;
  onCapture(): void;
  now(): number;
  setTimer(callback: () => void, delay: number): TimerId;
  clearTimer(id: TimerId): void;
  dendriticStart?: string;
}

export interface MazePursuitRuntime {
  start(): boolean;
  cancel(): void;
  getPhase(): MazePursuitPhase;
  getDendriticNode(): string;
}

/**
 * Consumes the virus's exact, contiguous slide segments. Each segment must
 * start at the dendritic cell's current node and every pair must be adjacent;
 * this prevents a late pursuer from visually cutting across a maze wall.
 */
export function createMazePursuitRuntime(
  dependencies: MazePursuitDependencies,
): MazePursuitRuntime {
  let phase: MazePursuitPhase = "idle";
  let dendriticNode = dependencies.dendriticStart ?? DENDRITIC_START;
  let startedAt = 0;
  let startTimer: TimerId | null = null;
  let stepTimer: TimerId | null = null;
  let deadlineTimer: TimerId | null = null;

  const clearPendingTimers = () => {
    for (const timer of [startTimer, stepTimer, deadlineTimer]) {
      if (timer !== null) dependencies.clearTimer(timer);
    }
    startTimer = null;
    stepTimer = null;
    deadlineTimer = null;
  };

  const capture = () => {
    if (phase === "captured" || phase === "cancelled") return;
    clearPendingTimers();
    phase = "captured";
    dependencies.onCapture();
  };

  const scheduleStep = (motionDurationMs = 0) => {
    if (phase !== "chasing" && phase !== "finale") return;
    const elapsed = Math.max(dependencies.now() - startedAt, 0);
    stepTimer = dependencies.setTimer(tick, motionDurationMs + getPursuitInterval(elapsed));
  };

  const tick = () => {
    stepTimer = null;
    if (phase !== "chasing" && phase !== "finale") return;

    const segment = dependencies.takeNextTrailSegment();
    if (!segment || segment.length < 2) {
      scheduleStep();
      return;
    }

    const hasValidStart = segment[0] === dendriticNode;
    const isContiguous = segment.every((nodeId, index) => {
      if (!dependencies.map.nodes[nodeId]) return false;
      if (index === 0) return true;
      return Object.values(dependencies.map.nodes[segment[index - 1]].exits).includes(nodeId);
    });
    if (!hasValidStart || !isContiguous) {
      scheduleStep();
      return;
    }

    const virusNode = dependencies.getVirusNode();
    const collisionIndex = segment.findIndex((nodeId) => nodeId === virusNode);
    const traversedSegment = collisionIndex >= 0 ? segment.slice(0, collisionIndex + 1) : segment;
    const nextNode = traversedSegment.at(-1) ?? dendriticNode;
    const elapsed = Math.max(dependencies.now() - startedAt, 0);
    const durationMs = getDendriticMoveDuration(traversedSegment.length, elapsed);
    dendriticNode = nextNode;
    dependencies.onDendriticMove(nextNode, durationMs);
    if (collisionIndex >= 0) {
      capture();
      return;
    }
    scheduleStep(durationMs);
  };

  const start = () => {
    if (phase !== "idle") return false;

    phase = "waiting";
    startedAt = dependencies.now();
    startTimer = dependencies.setTimer(() => {
      startTimer = null;
      if (phase !== "waiting") return;
      phase = "chasing";
      tick();
    }, PURSUIT_START_DELAY_MS);
    deadlineTimer = dependencies.setTimer(() => {
      deadlineTimer = null;
      if (phase !== "chasing") return;
      if (stepTimer !== null) dependencies.clearTimer(stepTimer);
      stepTimer = null;
      phase = "finale";
      dependencies.onFinaleStart?.();
      tick();
    }, PURSUIT_DEADLINE_MS);
    return true;
  };

  const cancel = () => {
    if (phase === "captured" || phase === "cancelled") return;
    clearPendingTimers();
    phase = "cancelled";
  };

  return {
    start,
    cancel,
    getPhase: () => phase,
    getDendriticNode: () => dendriticNode,
  };
}
