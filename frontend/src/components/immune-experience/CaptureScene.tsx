import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { immuneAssets } from "../../assets/immune/immuneAssets";
import type { ExploreCaptureSnapshot, Point, Size } from "./TissueExploreScene";
import { useReducedMotion } from "./useReducedMotion";

export const CAPTURE_DURATION_MS = 2_400;
export const REDUCED_CAPTURE_DURATION_MS = 50;
export const CAPTURE_VIRUS_ASPECT_RATIO = 1;
export const CAPTURE_TARGET_MAX_SCALE = 1.14;
export const CAPTURE_VIRUS_MAX_SCALE = 1.01;
export interface CaptureVirusKeyframe {
  translateX: number;
  translateY: number;
  rotateDegrees: number;
  scale: number;
}
export const CAPTURE_VIRUS_KEYFRAMES: readonly CaptureVirusKeyframe[] = [
  { translateX: 0, translateY: 0, rotateDegrees: 0, scale: 1 },
  { translateX: -4, translateY: 1, rotateDegrees: -2, scale: 1.01 },
  { translateX: 4, translateY: -1, rotateDegrees: 2, scale: .99 },
  { translateX: 18, translateY: -9, rotateDegrees: 0, scale: .18 },
] as const;
export const CAPTURE_PHASES = {
  nervousEnd: 20,
  dendriticEnd: 50,
  virusEnd: 78,
  backgroundEnd: 100,
} as const;

export type CaptureMode = "animation" | "video";
export type CaptureRenderer = "animation" | "video";

export interface CaptureSceneProps {
  mode: CaptureMode;
  videoSrc?: string;
  captureSnapshot?: ExploreCaptureSnapshot;
  onComplete: () => void;
}

export function getCaptureRenderer(
  mode: CaptureMode,
  videoSrc: string | undefined,
  videoFailed: boolean,
): CaptureRenderer {
  return mode === "video" && Boolean(videoSrc) && !videoFailed ? "video" : "animation";
}

export interface CaptureAabb {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export function getCaptureVirusAabb(
  position: Point,
  virus: Size,
  frame: CaptureVirusKeyframe,
  motionScale = 1,
): CaptureAabb {
  const radians = frame.rotateDegrees * Math.PI / 180;
  const halfWidth = virus.width * frame.scale / 2;
  const halfHeight = virus.height * frame.scale / 2;
  const extentX = Math.abs(Math.cos(radians)) * halfWidth
    + Math.abs(Math.sin(radians)) * halfHeight;
  const extentY = Math.abs(Math.sin(radians)) * halfWidth
    + Math.abs(Math.cos(radians)) * halfHeight;
  const centerX = position.x + virus.width / 2 + frame.translateX * motionScale;
  const centerY = position.y + virus.height / 2 + frame.translateY * motionScale;
  return {
    left: centerX - extentX,
    top: centerY - extentY,
    right: centerX + extentX,
    bottom: centerY + extentY,
  };
}

function getCaptureVirusEnvelope(virus: Size, motionScale: number): CaptureAabb {
  const frames = CAPTURE_VIRUS_KEYFRAMES.map((frame) => (
    getCaptureVirusAabb({ x: 0, y: 0 }, virus, frame, motionScale)
  ));
  return {
    left: Math.min(...frames.map((frame) => frame.left)),
    top: Math.min(...frames.map((frame) => frame.top)),
    right: Math.max(...frames.map((frame) => frame.right)),
    bottom: Math.max(...frames.map((frame) => frame.bottom)),
  };
}

export function fitCaptureVirusToStage(virus: Size, stage: Size): {
  virusSize: Size;
  motionScale: number;
} {
  const safeStage = {
    width: Math.max(0, Number.isFinite(stage.width) ? stage.width : 0),
    height: Math.max(0, Number.isFinite(stage.height) ? stage.height : 0),
  };
  const safeVirus = {
    width: Math.max(0, Number.isFinite(virus.width) ? virus.width : 0),
    height: Math.max(0, Number.isFinite(virus.height) ? virus.height : 0),
  };
  const translateWidth = Math.max(...CAPTURE_VIRUS_KEYFRAMES.map((frame) => frame.translateX))
    - Math.min(...CAPTURE_VIRUS_KEYFRAMES.map((frame) => frame.translateX));
  const translateHeight = Math.max(...CAPTURE_VIRUS_KEYFRAMES.map((frame) => frame.translateY))
    - Math.min(...CAPTURE_VIRUS_KEYFRAMES.map((frame) => frame.translateY));
  const motionScale = Math.min(
    1,
    translateWidth > 0 ? safeStage.width / translateWidth : 1,
    translateHeight > 0 ? safeStage.height / translateHeight : 1,
  );
  const fits = (scale: number) => {
    const envelope = getCaptureVirusEnvelope({
      width: safeVirus.width * scale,
      height: safeVirus.height * scale,
    }, motionScale);
    return envelope.right - envelope.left <= safeStage.width + 1e-9
      && envelope.bottom - envelope.top <= safeStage.height + 1e-9;
  };
  if (fits(1)) return { virusSize: safeVirus, motionScale };
  let low = 0;
  let high = 1;
  for (let iteration = 0; iteration < 48; iteration += 1) {
    const middle = (low + high) / 2;
    if (fits(middle)) low = middle;
    else high = middle;
  }
  return {
    virusSize: { width: safeVirus.width * low, height: safeVirus.height * low },
    motionScale,
  };
}

export function clampCapturePosition(
  point: Point,
  stage: Size,
  virus: Size,
  motionScale = 1,
): Point {
  const envelope = getCaptureVirusEnvelope(virus, motionScale);
  const minX = -envelope.left;
  const maxX = Math.max(
    minX,
    stage.width - envelope.right,
  );
  const minY = -envelope.top;
  const maxY = Math.max(
    minY,
    stage.height - envelope.bottom,
  );
  return {
    x: Math.min(Math.max(point.x, minX), maxX),
    y: Math.min(Math.max(point.y, minY), maxY),
  };
}

export function clampCaptureTargetPosition(center: Point, stage: Size, target: Size): Point {
  const halfVisualWidth = target.width * CAPTURE_TARGET_MAX_SCALE / 2;
  const halfVisualHeight = target.height * CAPTURE_TARGET_MAX_SCALE / 2;
  const safeCenter = {
    x: Math.min(
      Math.max(center.x, halfVisualWidth),
      Math.max(halfVisualWidth, stage.width - halfVisualWidth),
    ),
    y: Math.min(
      Math.max(center.y, halfVisualHeight),
      Math.max(halfVisualHeight, stage.height - halfVisualHeight),
    ),
  };
  return {
    x: safeCenter.x - target.width / 2,
    y: safeCenter.y - target.height / 2,
  };
}

export function scaleCapturePointToStage(point: Point, sourceStage: Size, stage: Size): Point {
  return {
    x: sourceStage.width > 0 ? point.x * stage.width / sourceStage.width : point.x,
    y: sourceStage.height > 0 ? point.y * stage.height / sourceStage.height : point.y,
  };
}

export function getFallbackVirusSize(width: number): Size {
  return { width, height: width * CAPTURE_VIRUS_ASPECT_RATIO };
}

export interface CaptureStageMetrics {
  clientWidth: number;
  clientHeight: number;
}

export interface CaptureImageMetrics {
  offsetWidth: number;
  offsetHeight: number;
  complete: boolean;
  naturalWidth: number;
}

export interface CaptureLayout {
  virusPosition: Point;
  virusSize: Size;
  virusMotionScale: number;
  targetPosition: Point;
}

export function measureCaptureLayout(
  stage: CaptureStageMetrics,
  virus: CaptureImageMetrics,
  target: CaptureImageMetrics,
  captureSnapshot?: ExploreCaptureSnapshot,
): CaptureLayout | null {
  const stageSize = { width: stage.clientWidth, height: stage.clientHeight };
  if (
    stageSize.width <= 0
    || stageSize.height <= 0
    || !virus.complete
    || virus.naturalWidth <= 0
    || virus.offsetWidth <= 0
    || virus.offsetHeight <= 0
    || !target.complete
    || target.naturalWidth <= 0
    || target.offsetWidth <= 0
    || target.offsetHeight <= 0
  ) return null;

  const sourceStage = captureSnapshot?.stageSize ?? stageSize;
  const sourcePosition = captureSnapshot?.virusPosition ?? DEFAULT_VIRUS_POSITION;
  const sourceTargetCenter = captureSnapshot?.targetCenter ?? DEFAULT_TARGET_CENTER;
  const fittedVirus = fitCaptureVirusToStage(
    { width: virus.offsetWidth, height: virus.offsetHeight },
    stageSize,
  );
  const virusSize = fittedVirus.virusSize;
  const targetSize = { width: target.offsetWidth, height: target.offsetHeight };

  return {
    virusPosition: clampCapturePosition(
      scaleCapturePointToStage(sourcePosition, sourceStage, stageSize),
      stageSize,
      virusSize,
      fittedVirus.motionScale,
    ),
    virusSize,
    virusMotionScale: fittedVirus.motionScale,
    targetPosition: clampCaptureTargetPosition(
      scaleCapturePointToStage(sourceTargetCenter, sourceStage, stageSize),
      stageSize,
      targetSize,
    ),
  };
}

interface CaptureLayoutObserver {
  observe: (target: object) => void;
  disconnect: () => void;
}

interface CreateCaptureLayoutRuntimeOptions {
  stage: CaptureStageMetrics;
  virus: CaptureImageMetrics;
  target: CaptureImageMetrics;
  captureSnapshot?: ExploreCaptureSnapshot;
  onLayout: (layout: CaptureLayout | null) => void;
  createObserver?: (callback: () => void) => CaptureLayoutObserver;
}

export function createCaptureLayoutRuntime({
  stage,
  virus,
  target,
  captureSnapshot,
  onLayout,
  createObserver = (callback) => {
    const observer = new ResizeObserver(callback);
    return {
      observe: (element) => observer.observe(element as Element),
      disconnect: () => observer.disconnect(),
    };
  },
}: CreateCaptureLayoutRuntimeOptions) {
  let disposed = false;
  const recalculate = () => {
    if (disposed) return;
    onLayout(measureCaptureLayout(stage, virus, target, captureSnapshot));
  };
  const observer = createObserver(recalculate);
  observer.observe(stage);
  observer.observe(virus);
  observer.observe(target);
  recalculate();

  return {
    recalculate,
    dispose: () => {
      if (disposed) return;
      disposed = true;
      observer.disconnect();
    },
  };
}

export function getCaptureDuration(prefersReducedMotion: boolean): number {
  return prefersReducedMotion ? REDUCED_CAPTURE_DURATION_MS : CAPTURE_DURATION_MS;
}

type CaptureTimer = number;
type SetCaptureTimer = (callback: () => void, delay: number) => CaptureTimer;
type ClearCaptureTimer = (timer: CaptureTimer) => void;

interface CreateCaptureRuntimeOptions {
  onComplete: () => void;
  setTimer?: SetCaptureTimer;
  clearTimer?: ClearCaptureTimer;
}

export type CaptureRuntimeEvent =
  | { type: "start-animation"; delay: number }
  | { type: "video-error" }
  | { type: "complete" }
  | { type: "cancel-animation" }
  | { type: "cancel" };

export interface CaptureRuntime {
  dispatch: (event: CaptureRuntimeEvent) => boolean;
  updateOnComplete: (onComplete: () => void) => CaptureRuntime;
}

export function createCaptureRuntime({
  onComplete,
  setTimer = (callback, timeout) => window.setTimeout(callback, timeout),
  clearTimer = (timer) => window.clearTimeout(timer),
}: CreateCaptureRuntimeOptions): CaptureRuntime {
  let settled = false;
  let videoFallbackActivated = false;
  let activeTimer: { id: CaptureTimer; delay: number; generation: number } | null = null;
  let timerGeneration = 0;
  let currentOnComplete = onComplete;

  const complete = () => {
    if (settled) return;

    settled = true;
    if (activeTimer) {
      clearTimer(activeTimer.id);
      activeTimer = null;
    }
    currentOnComplete();
  };

  const startAnimation = (delay: number) => {
    if (settled || activeTimer?.delay === delay) return;

    if (activeTimer) clearTimer(activeTimer.id);
    const generation = ++timerGeneration;
    let firedSynchronously = false;
    const id = setTimer(() => {
      firedSynchronously = true;
      if (generation !== timerGeneration || settled) return;

      activeTimer = null;
      complete();
    }, delay);
    if (!firedSynchronously && !settled) activeTimer = { id, delay, generation };
  };

  const cancelAnimation = () => {
    timerGeneration += 1;
    if (activeTimer) {
      clearTimer(activeTimer.id);
      activeTimer = null;
    }
  };

  const runtime: CaptureRuntime = {
    dispatch: (event) => {
      switch (event.type) {
        case "start-animation":
          startAnimation(event.delay);
          return false;
        case "video-error":
          if (settled || videoFallbackActivated) return false;

          videoFallbackActivated = true;
          return true;
        case "complete":
          complete();
          return false;
        case "cancel-animation":
          cancelAnimation();
          return false;
        case "cancel":
          cancelAnimation();
          return false;
      }
    },
    updateOnComplete: (nextOnComplete) => {
      currentOnComplete = nextOnComplete;
      return runtime;
    },
  };

  return runtime;
}

const DEFAULT_VIRUS_POSITION: Point = { x: 48, y: 170 };
const DEFAULT_TARGET_CENTER: Point = { x: 520, y: 110 };
export function CaptureScene({ mode, videoSrc, captureSnapshot, onComplete }: CaptureSceneProps) {
  const prefersReducedMotion = useReducedMotion();
  const [videoFailed, setVideoFailed] = useState(false);
  const [layout, setLayout] = useState<CaptureLayout | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const virusRef = useRef<HTMLImageElement>(null);
  const targetRef = useRef<HTMLImageElement>(null);
  const reclampRef = useRef<(() => void) | null>(null);
  const runtimeRef = useRef<CaptureRuntime | null>(null);
  if (!runtimeRef.current) runtimeRef.current = createCaptureRuntime({ onComplete });
  const runtime = runtimeRef.current.updateOnComplete(onComplete);

  const renderer = getCaptureRenderer(mode, videoSrc, videoFailed);
  const layoutReady = layout !== null;
  const finish = useCallback(() => runtime.dispatch({ type: "complete" }), [runtime]);
  const handleVideoError = useCallback(() => {
    const activated = runtime.dispatch({
      type: "video-error",
    });
    if (activated) setVideoFailed(true);
  }, [runtime]);

  useEffect(() => {
    if (renderer !== "animation" || !layoutReady) return;

    runtime.dispatch({
      type: "start-animation",
      delay: getCaptureDuration(prefersReducedMotion),
    });

    return () => {
      runtime.dispatch({ type: "cancel-animation" });
    };
  }, [layoutReady, prefersReducedMotion, renderer, runtime]);

  useEffect(() => () => {
    runtime.dispatch({ type: "cancel" });
  }, [runtime]);

  useLayoutEffect(() => {
    if (renderer !== "animation") return;

    const stage = stageRef.current;
    const virus = virusRef.current;
    const target = targetRef.current;
    if (!stage || !virus || !target) return;

    const layoutRuntime = createCaptureLayoutRuntime({
      stage,
      virus,
      target,
      captureSnapshot,
      onLayout: setLayout,
    });
    reclampRef.current = layoutRuntime.recalculate;

    return () => {
      if (reclampRef.current === layoutRuntime.recalculate) reclampRef.current = null;
      layoutRuntime.dispose();
    };
  }, [captureSnapshot, renderer]);

  if (renderer === "video" && videoSrc) {
    return (
      <section className="immune-level-scene immune-capture-scene immune-capture-video-scene" aria-labelledby="immune-capture-title">
        <div className="immune-capture-copy">
          <p className="immune-level-kicker">病毒日记 · 第一关</p>
          <h2 id="immune-capture-title">免疫巡逻员识别抗原</h2>
        </div>
        <video
          className="immune-capture-video"
          src={videoSrc}
          autoPlay
          muted
          playsInline
          aria-label="树突状细胞识别疫苗抗原的科普动画"
          onEnded={finish}
          onError={handleVideoError}
        />
        <p className="immune-medical-note">仅供科普参考，不能替代专业医疗建议。</p>
      </section>
    );
  }

  const virusStyle = {
    ...(layout
      ? {
        "--immune-capture-virus-x": `${layout.virusPosition.x}px`,
        "--immune-capture-virus-y": `${layout.virusPosition.y}px`,
        "--immune-capture-virus-width": `${layout.virusSize.width}px`,
        "--immune-capture-virus-height": `${layout.virusSize.height}px`,
        "--immune-capture-jitter-left-x": `${-4 * layout.virusMotionScale}px`,
        "--immune-capture-jitter-left-y": `${layout.virusMotionScale}px`,
        "--immune-capture-jitter-right-x": `${4 * layout.virusMotionScale}px`,
        "--immune-capture-jitter-right-y": `${-layout.virusMotionScale}px`,
        "--immune-capture-virus-end-x": `${18 * layout.virusMotionScale}px`,
        "--immune-capture-virus-end-y": `${-9 * layout.virusMotionScale}px`,
      }
      : {}),
  } as CSSProperties;
  const targetStyle = {
    ...(layout
      ? {
        "--immune-capture-target-x": `${layout.targetPosition.x}px`,
        "--immune-capture-target-y": `${layout.targetPosition.y}px`,
      }
      : {}),
  } as CSSProperties;

  return (
    <section
      className="immune-level-scene immune-capture-scene immune-capture-animation-scene"
      aria-label="树突状细胞识别抗原动画"
      data-reduced-motion={prefersReducedMotion}
    >
      <div className="immune-capture-stage" ref={stageRef} data-layout-ready={layoutReady}>
        <img className="immune-capture-background" src={immuneAssets.tissueBackground} alt="" aria-hidden="true" />
        <span className="immune-capture-shade" aria-hidden="true" />
        <img
          ref={targetRef}
          className="immune-capture-dendritic"
          src={immuneAssets.dendriticCell}
          style={targetStyle}
          alt="正在识别抗原的树突状细胞"
          onLoad={() => reclampRef.current?.()}
        />
        <img
          ref={virusRef}
          className="immune-capture-virus"
          src={immuneAssets.virusNervous}
          style={virusStyle}
          alt="感到紧张并逐渐淡出的病毒角色"
          onLoad={() => reclampRef.current?.()}
        />
        <p className="immune-capture-status" role="status" aria-live="polite">
          树突状细胞已发现疫苗抗原，正在完成识别。
        </p>
      </div>
    </section>
  );
}
