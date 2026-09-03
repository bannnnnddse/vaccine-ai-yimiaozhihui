import type { CSSProperties } from "react";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import type { LevelThreePhase } from "./levelThreeState";

export const IMMUNE_OUTCOME_SCENES = [
  { id: "phagocytosis", title: "被吞噬清除" },
  { id: "complement", title: "激活补体裂解" },
  { id: "neutralization", title: "中和失活" },
] as const;

interface ImmuneOutcomeScenesProps {
  phase: Extract<LevelThreePhase, "outcome-scenes" | "outcome-exit">;
}

const DEBRIS = [
  { x: -74, y: -34, size: 17, rotation: -28 },
  { x: -48, y: 48, size: 13, rotation: 36 },
  { x: -12, y: -61, size: 10, rotation: 74 },
  { x: 30, y: -48, size: 15, rotation: 118 },
  { x: 66, y: -18, size: 12, rotation: 166 },
  { x: 54, y: 46, size: 18, rotation: 214 },
  { x: 8, y: 62, size: 11, rotation: 258 },
] as const;

type OutcomeId = (typeof IMMUNE_OUTCOME_SCENES)[number]["id"];

function BoundAntibodies({ outcome, falling = false }: { outcome: OutcomeId; falling?: boolean }) {
  return [1, 2].map((number) => (
    <img
      key={number}
      className={`immune-outcome-scenes__antibody is-${outcome} is-antibody-${number}${falling ? " is-falling" : ""}`}
      data-outcome-antibody={`${outcome}-${number}`}
      src={level3Assets.redAntibody}
      alt=""
      aria-hidden="true"
      draggable={false}
    />
  ));
}

export function ImmuneOutcomeScenes({ phase }: ImmuneOutcomeScenesProps) {
  return (
    <section className={`immune-outcome-scenes-wrap${phase === "outcome-exit" ? " is-exiting" : ""}`} aria-label="抗体作用后的三种免疫结局">
      <h2 className="immune-outcome-scenes__title">病毒的三个结局</h2>
      <ol className="immune-outcome-scenes">
        <li className="immune-outcome-scene is-phagocytosis" data-outcome-scene="被吞噬清除" aria-label="被吞噬清除：巨噬细胞吞噬被抗体标记的病毒">
          <h3>被吞噬清除</h3>
          <div className="immune-outcome-scenes__virus-cluster is-phagocytosis-target" aria-hidden="true">
            <img className="immune-outcome-scenes__virus" src={level3Assets.virus} alt="" draggable={false} />
            <BoundAntibodies outcome="phagocytosis" />
          </div>
          <img className="immune-outcome-scenes__macrophage" src={level3Assets.outcomeMacrophage} alt="" aria-hidden="true" draggable={false} />
        </li>

        <li className="immune-outcome-scene is-complement" data-outcome-scene="激活补体裂解" aria-label="激活补体裂解：病毒包膜破裂并炸成紫色颗粒">
          <h3>激活补体裂解</h3>
          <div className="immune-outcome-scenes__virus-cluster is-complement-target" aria-hidden="true">
            <img className="immune-outcome-scenes__virus is-complement-original" src={level3Assets.virus} alt="" draggable={false} />
            <img className="immune-outcome-scenes__virus is-ruptured" src={level3Assets.outcomeVirusRuptured} alt="" draggable={false} />
            <BoundAntibodies outcome="complement" falling />
            {DEBRIS.map((particle, index) => (
              <span
                className="immune-outcome-scenes__debris"
                key={index}
                style={{
                  "--outcome-debris-x": `${particle.x}px`,
                  "--outcome-debris-y": `${particle.y}px`,
                  "--outcome-debris-size": `${particle.size}px`,
                  "--outcome-debris-rotation": `${particle.rotation}deg`,
                } as CSSProperties}
              />
            ))}
          </div>
        </li>

        <li className="immune-outcome-scene is-neutralization" data-outcome-scene="中和失活" aria-label="中和失活：病毒先出现恶心表情，随后死亡失活">
          <h3>中和失活</h3>
          <div className="immune-outcome-scenes__virus-cluster is-neutralization-target" aria-hidden="true">
            <img className="immune-outcome-scenes__virus is-neutralization-original" src={level3Assets.virus} alt="" draggable={false} />
            <img className="immune-outcome-scenes__virus is-nauseated" src={level3Assets.outcomeVirusNauseated} alt="" draggable={false} />
            <img className="immune-outcome-scenes__virus is-dead" src={level3Assets.outcomeVirusDead} alt="" draggable={false} />
            <BoundAntibodies outcome="neutralization" />
          </div>
        </li>
      </ol>
    </section>
  );
}
