import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { immuneAssets } from "../../assets/immune/immuneAssets";
import { useReducedMotion } from "./useReducedMotion";

export const INJECTION_DURATION_MS = 4_000;
export const REDUCED_MOTION_DURATION_MS = 50;

export function getInjectionDuration(prefersReducedMotion: boolean): number {
  return prefersReducedMotion ? REDUCED_MOTION_DURATION_MS : INJECTION_DURATION_MS;
}

type InjectionTimer = number;
type SetInjectionTimer = (callback: () => void, delay: number) => InjectionTimer;
type ClearInjectionTimer = (timer: InjectionTimer) => void;

interface ScheduleInjectionCompletionOptions {
  delay: number;
  onComplete: () => void;
  setTimer?: SetInjectionTimer;
  clearTimer?: ClearInjectionTimer;
}

export interface InjectionCompletionSchedule {
  finish: () => void;
  cancel: () => void;
}

export function scheduleInjectionCompletion({
  delay,
  onComplete,
  setTimer = (callback, timeout) => window.setTimeout(callback, timeout),
  clearTimer = (timer) => window.clearTimeout(timer),
}: ScheduleInjectionCompletionOptions): InjectionCompletionSchedule {
  let completed = false;
  const finish = () => {
    if (completed) return;

    completed = true;
    onComplete();
  };
  const timer = setTimer(finish, delay);

  return {
    finish,
    cancel: () => clearTimer(timer),
  };
}

export interface InjectionSceneProps {
  onComplete: () => void;
}

const antigens = [
  { id: 1, delay: "1.45s" },
  { id: 2, delay: "1.63s" },
  { id: 3, delay: "1.81s" },
  { id: 4, delay: "1.99s" },
] as const;
const particles = [
  ["17%", "12%", "1.6s"],
  ["29%", "25%", "1.72s"],
  ["41%", "38%", "1.84s"],
  ["53%", "12%", "1.96s"],
  ["65%", "25%", "2.08s"],
  ["77%", "38%", "2.2s"],
] as const;

export function InjectionScene({ onComplete }: InjectionSceneProps) {
  const prefersReducedMotion = useReducedMotion();
  const onCompleteRef = useRef(onComplete);
  const hasContinuedRef = useRef(false);
  const [isReadyToContinue, setIsReadyToContinue] = useState(false);
  onCompleteRef.current = onComplete;

  const continueToNextScene = useCallback(() => {
    if (!isReadyToContinue || hasContinuedRef.current) return;

    hasContinuedRef.current = true;
    onCompleteRef.current();
  }, [isReadyToContinue]);

  useEffect(() => {
    const schedule = scheduleInjectionCompletion({
      delay: getInjectionDuration(prefersReducedMotion),
      onComplete: () => setIsReadyToContinue(true),
    });
    return () => {
      schedule.cancel();
    };
  }, [prefersReducedMotion]);

  return (
    <section
      className="immune-level-scene immune-injection-scene"
      aria-label="疫苗抗原接种动画"
      data-reduced-motion={prefersReducedMotion}
      data-ready-to-continue={isReadyToContinue}
      onClick={continueToNextScene}
    >
      <div className="immune-injection-stage">
        <img
          className="immune-injection-skin"
          src={immuneAssets.skinLayer}
          alt="疫苗接种部位的皮肤组织剖面"
        />
        <img
          className="immune-injection-needle"
          src={immuneAssets.needle}
          alt=""
          aria-hidden="true"
        />

        <div className="immune-injection-antigens" aria-hidden="true">
          {antigens.map(({ id, delay }) => (
            <span
              className="immune-injection-antigen"
              key={id}
              style={{
                "--immune-delay": delay,
                "--immune-virus-start-left": `var(--immune-virus-${id}-start-left)`,
                "--immune-virus-start-top": `var(--immune-virus-${id}-start-top)`,
                "--immune-virus-end-left": `var(--immune-virus-${id}-end-left)`,
                "--immune-virus-end-top": `var(--immune-virus-${id}-end-top)`,
              } as CSSProperties}
            >
              <img src={immuneAssets.injectionVirus} alt="" />
            </span>
          ))}
        </div>

        <div className="immune-injection-particles" aria-hidden="true">
          {particles.map(([left, bottom, delay]) => (
            <span
              className="immune-injection-particle"
              key={`${left}-${bottom}`}
              style={{
                "--immune-left": left,
                "--immune-bottom": bottom,
                "--immune-delay": delay,
              } as CSSProperties}
            />
          ))}
        </div>

        <span className="immune-injection-flash" aria-hidden="true" />
      </div>

      <p className="immune-injection-status sr-only" role="status" aria-live="polite">
        {isReadyToContinue ? "动画播放完成，点击屏幕任意处继续。" : "正在演示疫苗抗原进入接种部位的局部组织。"}
      </p>
    </section>
  );
}
