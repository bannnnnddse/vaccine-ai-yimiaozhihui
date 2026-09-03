import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import { useReducedMotion } from "../useReducedMotion";
import { DendriticAI } from "./DendriticAI";
import { getMazeBoardLayout, MazeRenderer } from "./MazeRenderer";
import {
  DENDRITIC_START,
  MAZE,
  VIRUS_START,
  getDirectionalPath,
  type MazeDirection,
} from "./mazeMap";
import { getDirectionFromKey, getSwipeDirection } from "./mazeMovement";
import { createMazePursuitRuntime, type MazePursuitRuntime } from "./mazePursuit";
import { VirusPlayer } from "./VirusPlayer";

const MINIMUM_SWIPE_DISTANCE_PX = 24;
const VIRUS_DIAMETER_IN_CELLS = 0.64;
const VIRUS_MILLISECONDS_PER_CELL = 72;
export const MAZE_INTRO_HOLD_DURATION_MS = 30_000;
export const MAZE_CAPTURE_ANIMATION_MS = 900;

export interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface MazeCaptureSnapshot {
  virusPosition: Point;
  targetCenter: Point;
  stageSize: Size;
}

export interface MazeGameProps {
  onCapture(snapshot: MazeCaptureSnapshot): void;
}

function getNodeCenter(nodeId: string, stageSize: Size): Point {
  const node = MAZE.nodes[nodeId];
  const layout = getMazeBoardLayout(MAZE, stageSize);
  return {
    x: layout.left + (node.col + 0.5) * layout.cellSize,
    y: layout.top + (node.row + 0.5) * layout.cellSize,
  };
}

function getVirusTopLeft(nodeId: string, stageSize: Size): Point {
  const center = getNodeCenter(nodeId, stageSize);
  const diameter = getMazeBoardLayout(MAZE, stageSize).cellSize * VIRUS_DIAMETER_IN_CELLS;
  return {
    x: center.x - diameter / 2,
    y: center.y - diameter / 2,
  };
}

/** Composes map, player input, and the deterministic dendritic-cell pursuit. */
export function MazeGame({ onCapture }: MazeGameProps) {
  const prefersReducedMotion = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const mazeCanvasRef = useRef<HTMLDivElement | null>(null);
  const pointerStartRef = useRef<Point | null>(null);
  const runtimeRef = useRef<MazePursuitRuntime | null>(null);
  const captureAnimationTimerRef = useRef<ReturnType<typeof globalThis.setTimeout> | null>(null);
  const introTimerRef = useRef<ReturnType<typeof globalThis.setTimeout> | null>(null);
  const introExitTimerRef = useRef<ReturnType<typeof globalThis.setTimeout> | null>(null);
  const introDismissedRef = useRef(false);
  const virusNodeRef = useRef(VIRUS_START);
  const virusTrailSegmentsRef = useRef<string[][]>([[DENDRITIC_START, VIRUS_START]]);
  const dendriticNodeRef = useRef(DENDRITIC_START);
  const inputLockedRef = useRef(false);
  const captureHandledRef = useRef(false);
  const onCaptureRef = useRef(onCapture);
  const [virusNode, setVirusNode] = useState(VIRUS_START);
  const [dendriticNode, setDendriticNode] = useState(DENDRITIC_START);
  const [virusMotionDuration, setVirusMotionDuration] = useState(230);
  const [dendriticMotionDuration, setDendriticMotionDuration] = useState(180);
  const [pursuitPhase, setPursuitPhase] = useState<"idle" | "waiting" | "chasing" | "finale" | "captured">("idle");
  const [introPhase, setIntroPhase] = useState<"visible" | "leaving" | "hidden">("visible");
  const [status, setStatus] = useState("使用方向键或滑动来移动病毒。");

  onCaptureRef.current = onCapture;

  useLayoutEffect(() => {
    mazeCanvasRef.current = stageRef.current?.querySelector<HTMLDivElement>(".immune-maze") ?? null;

    return () => {
      mazeCanvasRef.current = null;
    };
  }, []);

  useEffect(() => {
    stageRef.current?.focus({ preventScroll: true });
  }, []);

  const beginIntroExit = useCallback(() => {
    if (introDismissedRef.current) return;
    introDismissedRef.current = true;
    if (introTimerRef.current !== null) {
      globalThis.clearTimeout(introTimerRef.current);
      introTimerRef.current = null;
    }
    setIntroPhase("leaving");
    introExitTimerRef.current = globalThis.setTimeout(() => {
      introExitTimerRef.current = null;
      setIntroPhase("hidden");
    }, 360);
  }, []);

  useEffect(() => {
    introTimerRef.current = globalThis.setTimeout(beginIntroExit, MAZE_INTRO_HOLD_DURATION_MS);
    return () => {
      if (introTimerRef.current !== null) globalThis.clearTimeout(introTimerRef.current);
      if (introExitTimerRef.current !== null) globalThis.clearTimeout(introExitTimerRef.current);
    };
  }, [beginIntroExit]);

  const freezeAfterCapture = useCallback(() => {
    if (captureHandledRef.current) return;

    captureHandledRef.current = true;
    inputLockedRef.current = true;
    runtimeRef.current?.cancel();
    setPursuitPhase("captured");
    setStatus("树突状细胞已捕获病毒。");

    const rect = mazeCanvasRef.current?.getBoundingClientRect();
    const stageSize = {
      width: rect?.width ?? 0,
      height: rect?.height ?? 0,
    };
    const snapshot = {
      virusPosition: getVirusTopLeft(virusNodeRef.current, stageSize),
      targetCenter: getNodeCenter(dendriticNodeRef.current, stageSize),
      stageSize,
    };
    captureAnimationTimerRef.current = globalThis.setTimeout(() => {
      captureAnimationTimerRef.current = null;
      onCaptureRef.current(snapshot);
    }, MAZE_CAPTURE_ANIMATION_MS);
  }, []);

  const startPursuit = useCallback(() => {
    if (inputLockedRef.current || runtimeRef.current) return;

    const runtime = createMazePursuitRuntime({
      map: MAZE,
      getVirusNode: () => virusNodeRef.current,
      takeNextTrailSegment: () => virusTrailSegmentsRef.current.shift(),
      onDendriticMove: (nextNode, durationMs) => {
        dendriticNodeRef.current = nextNode;
        setDendriticMotionDuration(durationMs);
        setDendriticNode(nextNode);
        const phase = runtimeRef.current?.getPhase();
        setPursuitPhase(phase === "finale" ? "finale" : "chasing");
        setStatus(phase === "finale" ? "免疫追踪已收紧，树突状细胞正在完成捕获。" : "树突状细胞正在追击病毒。");
      },
      onFinaleStart: () => {
        inputLockedRef.current = true;
        setPursuitPhase("finale");
        setStatus("免疫追踪已锁定病毒，正在沿最短通道收网。");
      },
      onCapture: freezeAfterCapture,
      now: () => Date.now(),
      setTimer: (callback, delay) => globalThis.setTimeout(callback, delay),
      clearTimer: (timer) => globalThis.clearTimeout(timer),
    });

    runtimeRef.current = runtime;
    if (runtime.start()) {
      setPursuitPhase("waiting");
      setStatus("树突状细胞正在锁定病毒。");
    }
  }, [freezeAfterCapture]);

  const moveVirus = useCallback((direction: MazeDirection) => {
    if (inputLockedRef.current) return;

    const path = getDirectionalPath(MAZE, virusNodeRef.current, direction);
    const nextNode = path.at(-1) ?? virusNodeRef.current;
    if (nextNode === virusNodeRef.current) {
      setStatus("这个方向没有可通行的路线。");
      return;
    }

    const collisionNode = path.find((nodeId) => nodeId === dendriticNodeRef.current);
    if (collisionNode) {
      virusNodeRef.current = collisionNode;
      setVirusNode(collisionNode);
      freezeAfterCapture();
      return;
    }

    virusNodeRef.current = nextNode;
    virusTrailSegmentsRef.current.push(path);
    setVirusMotionDuration(Math.max(180, (path.length - 1) * VIRUS_MILLISECONDS_PER_CELL));
    setVirusNode(nextNode);
    setStatus("病毒已移动，继续躲避树突状细胞。");
    startPursuit();
  }, [freezeAfterCapture, startPursuit]);

  const handleKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    const direction = getDirectionFromKey(event.key);
    if (!direction) return;

    event.preventDefault();
    beginIntroExit();
    moveVirus(direction);
  }, [beginIntroExit, moveVirus]);

  const rememberPointer = useCallback((event: PointerEvent<HTMLDivElement>) => {
    beginIntroExit();
    if (inputLockedRef.current) return;
    pointerStartRef.current = { x: event.clientX, y: event.clientY };
  }, [beginIntroExit]);

  const handleSwipe = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const start = pointerStartRef.current;
    pointerStartRef.current = null;
    if (!start || inputLockedRef.current) return;

    const delta = { x: event.clientX - start.x, y: event.clientY - start.y };
    if (Math.max(Math.abs(delta.x), Math.abs(delta.y)) < MINIMUM_SWIPE_DISTANCE_PX) {
      setStatus("滑动距离不足，请滑动至少 24 像素。");
      return;
    }

    const direction = getSwipeDirection(delta);
    if (direction) moveVirus(direction);
  }, [moveVirus]);

  const cancelSwipe = useCallback(() => {
    pointerStartRef.current = null;
  }, []);

  useEffect(() => () => {
    runtimeRef.current?.cancel();
    runtimeRef.current = null;
    if (captureAnimationTimerRef.current !== null) {
      globalThis.clearTimeout(captureAnimationTimerRef.current);
      captureAnimationTimerRef.current = null;
    }
    if (introTimerRef.current !== null) globalThis.clearTimeout(introTimerRef.current);
    if (introExitTimerRef.current !== null) globalThis.clearTimeout(introExitTimerRef.current);
  }, []);

  const captured = pursuitPhase === "captured";
  const virusVisualState = captured ? "captured" : pursuitPhase === "idle" ? "idle" : "moving";
  const dendriticVisualState = captured ? "captured" : pursuitPhase === "finale" ? "chasing" : pursuitPhase;

  return (
    <div
      ref={stageRef}
      className="immune-maze-game"
      role="application"
      aria-label="免疫追逐迷宫"
      tabIndex={0}
      data-reduced-motion={prefersReducedMotion}
      data-pursuit-phase={pursuitPhase}
      data-intro-phase={introPhase}
      data-capture-animation={captured ? "playing" : "idle"}
      style={{ touchAction: "none", ...(prefersReducedMotion ? { transition: "none" } : {}) }}
      onKeyDown={handleKeyDown}
      onPointerDown={rememberPointer}
      onPointerUp={handleSwipe}
      onPointerCancel={cancelSwipe}
    >
      <p className="sr-only" role="status" aria-live="polite">{status}</p>
      <MazeRenderer map={MAZE}>
        <VirusPlayer node={virusNode} visualState={virusVisualState} motionDurationMs={virusMotionDuration} />
        <DendriticAI node={dendriticNode} visualState={dendriticVisualState} motionDurationMs={dendriticMotionDuration} />
      </MazeRenderer>
      {introPhase !== "hidden" && (
        <div className={`immune-maze__intro is-${introPhase}`} data-maze-intro={introPhase} aria-hidden="true">
          <p>通过↑↓←→ / WASD操控病毒颗粒</p>
          <p>躲避树突状细胞的追击！</p>
        </div>
      )}
    </div>
  );
}
