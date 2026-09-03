import { useEffect, useReducer, useRef, useState, type CSSProperties, type MouseEvent, type PointerEvent } from "react";
import { immuneAssets } from "../../assets/immune/immuneAssets";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import {
  SWALLOW_DURATION_MS,
  INITIAL_ANTIGEN_PRESENTATION_STATE,
  transitionAntigenPresentation,
} from "./antigenPresentationState";

type CaptureStyle = CSSProperties & Record<
  | "--struggle"
  | "--virus-left"
  | "--virus-top"
  | "--virus-rotate"
  | "--virus-scale"
  | "--swallow-progress"
  | "--cell-nudge"
  | "--cell-tilt",
  string
>;

const STRUGGLE_FRAMES = [
  immuneAssets.antigenVirusStruggleLeftV2,
  immuneAssets.antigenVirusStruggleCenterV2,
  immuneAssets.antigenVirusStruggleRightV2,
  immuneAssets.antigenVirusStruggleCenterV2,
] as const;

export interface AntigenPresentationSceneProps { onEnded: () => void; }

function easeInCubic(value: number): number {
  return value * value * value;
}

export function AntigenPresentationScene({ onEnded }: AntigenPresentationSceneProps) {
  const [state, dispatch] = useReducer(transitionAntigenPresentation, INITIAL_ANTIGEN_PRESENTATION_STATE);
  const [reducedMotion, setReducedMotion] = useState(false);
  const frameRef = useRef<number | null>(null);
  const lastFrameRef = useRef<number | null>(null);
  const endedRef = useRef(false);
  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (state.shouldExit) return;
    const tick = (now: number) => {
      const previous = lastFrameRef.current ?? now;
      lastFrameRef.current = now;
      dispatch({ type: "frame", deltaMs: Math.max(0, now - previous) });
      frameRef.current = window.requestAnimationFrame(tick);
    };
    frameRef.current = window.requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      lastFrameRef.current = null;
    };
  }, [state.shouldExit]);

  useEffect(() => {
    if (!state.shouldExit || endedRef.current) return;
    endedRef.current = true;
    onEndedRef.current();
  }, [state.shouldExit]);

  const canStruggle = state.phase === "struggling";
  const isStrained = canStruggle && state.struggle > 0.12;
  const swallowProgress = state.phase === "swallowing"
    ? Math.min(1, state.phaseElapsedMs / SWALLOW_DURATION_MS)
    : state.phase === "complete" ? 1 : 0;
  const pullProgress = state.phase === "swallowing" || state.phase === "complete"
    ? 0.78 + easeInCubic(swallowProgress) * 0.22
    : state.progress * 0.78;
  const strugglePeriod = Math.max(30, 58 - state.struggle * 24);
  const wobble = canStruggle && !reducedMotion
    ? Math.sin(state.captureElapsedMs / strugglePeriod) * (0.7 + state.struggle * 4.8)
    : 0;
  const verticalWobble = canStruggle && !reducedMotion
    ? Math.sin(state.captureElapsedMs / (strugglePeriod * 1.7)) * state.struggle * 1.4
    : 0;
  const virusLeft = 19 + pullProgress * 40 + wobble;
  const virusTop = 52 + verticalWobble;
  const virusScale = state.phase === "swallowing"
    ? Math.max(0.12, 0.88 - swallowProgress * 0.76)
    : Math.max(0.78, 1 - state.progress * 0.16);
  const frameIndex = reducedMotion
    ? 1
    : Math.floor(state.captureElapsedMs / Math.max(70, 145 - state.struggle * 60)) % STRUGGLE_FRAMES.length;
  const virus = state.phase === "swallowing"
    ? immuneAssets.antigenVirusSwallowV2
    : STRUGGLE_FRAMES[frameIndex];
  const cell = state.phase === "swallowing"
    ? immuneAssets.dendriticCaptureSwallowV2
    : state.phase === "complete"
      ? immuneAssets.dendriticSideSatisfied
      : isStrained
        ? immuneAssets.dendriticCaptureStrainedV2
        : immuneAssets.dendriticSideHolding;

  const sceneStyle: CaptureStyle = {
    "--struggle": state.struggle.toFixed(3),
    "--virus-left": `${virusLeft.toFixed(3)}%`,
    "--virus-top": `${virusTop.toFixed(3)}%`,
    "--virus-rotate": `${(wobble * 3.6).toFixed(2)}deg`,
    "--virus-scale": virusScale.toFixed(3),
    "--swallow-progress": swallowProgress.toFixed(3),
    "--cell-nudge": `${(-state.struggle * 9).toFixed(2)}px`,
    "--cell-tilt": `${(-state.struggle * 0.9).toFixed(2)}deg`,
  };

  const status = state.phase === "grabbing"
    ? "树突状细胞正在抓牢病毒，挣扎即将开始。"
    : state.phase === "struggling"
      ? "病毒正在挣扎。按“挣扎！”可暂时拖慢摄取。"
      : state.phase === "swallowing"
        ? "树突状细胞正在吞下病毒抗原。"
        : "病毒抗原已被摄取，正在进入下一环节。";

  const struggle = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (canStruggle) dispatch({ type: "struggle" });
  };
  const stopPointerPropagation = (event: PointerEvent<HTMLButtonElement>) => {
    event.stopPropagation();
  };

  return (
    <section
      className={`immune-capture immune-capture--${state.phase}${isStrained ? " immune-capture--strained" : ""}`}
      style={sceneStyle}
      aria-label="树突状细胞抓住、拖拽并摄取病毒抗原的互动场景"
    >
      <img className="immune-capture__background" src={level3Assets.background} alt="" aria-hidden="true" />
      <p className="immune-capture__narrative" aria-hidden="true">病毒被树突状细胞摄取过程</p>
      <div className="immune-capture__stage" aria-hidden="true">
        <img className="immune-capture__cell" src={cell} alt="" />
        {state.phase !== "complete" && <>
          <img className="immune-capture__arm immune-capture__arm--upper" src={immuneAssets.dendriticCaptureArmUpperV2} alt="" />
          <img className="immune-capture__arm immune-capture__arm--lower" src={immuneAssets.dendriticCaptureArmLowerV2} alt="" />
          <img className="immune-capture__virus" src={virus} alt="" />
          <span className="immune-capture__grip-glow" />
        </>}
      </div>
      <div className="immune-capture__hud">
        {(state.phase === "grabbing" || state.phase === "struggling") && <>
          <button
            className="immune-capture__struggle"
            type="button"
            disabled={!canStruggle}
            aria-label={canStruggle ? "挣扎！" : "抓牢中，稍后可以挣扎"}
            onPointerDown={stopPointerPropagation}
            onClick={struggle}
          >
            挣扎！
          </button>
        </>}
      </div>
      <p className="sr-only" role="status" aria-live="polite">{status}</p>
    </section>
  );
}
