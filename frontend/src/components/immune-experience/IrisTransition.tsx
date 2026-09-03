import type { LevelThreePhase } from "./levelThreeState";

type IrisTransitionPhase = Extract<
  LevelThreePhase,
  "iris-focus" | "iris-hold" | "iris-close" | "blackout"
>;

export interface IrisTransitionProps {
  phase: IrisTransitionPhase;
}

export function IrisTransition({ phase }: IrisTransitionProps) {
  return (
    <div
      className={`immune-iris-transition is-${phase}`}
      data-iris-transition
      aria-hidden="true"
    >
      <span className="immune-iris-transition__aperture" />
    </div>
  );
}
