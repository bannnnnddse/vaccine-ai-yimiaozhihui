import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { SpeechBubble } from "./SpeechBubble";

export type BCellPatrolPhase = "b-cell-patrol-intro" | "b-cell-patrol" | "b-cell-patrol-caught";

export function BCellPatrol({ phase }: { phase: BCellPatrolPhase }) {
  if (phase === "b-cell-patrol-intro") {
    return (
      <div className="immune-b-cell-patrol is-intro">
        <div className="immune-b-cell-patrol__departing-b" data-patrol-b-cell-turn aria-hidden="true">
          <img
            className="immune-b-cell-patrol__turn-face is-before"
            src={level3Assets.bCell}
            alt=""
            draggable={false}
          />
          <img
            className="immune-b-cell-patrol__turn-face is-after"
            src={level3Assets.bCellPatrol}
            alt=""
            draggable={false}
          />
        </div>
        <img className="immune-b-cell-patrol__departing-helper" src={level3Assets.helperTCell} alt="" draggable={false} />
      </div>
    );
  }

  const caught = phase === "b-cell-patrol-caught";
  return (
    <div className={`immune-b-cell-patrol is-${caught ? "caught" : "moving"}`}>
      {[1, 2, 3].map((index) => (
        <img
          className={`immune-b-cell-patrol__virus is-virus-${index}`}
          src={level3Assets.patrolVirus}
          alt=""
          draggable={false}
          key={index}
        />
      ))}
      <div className="immune-b-cell-patrol__b-cell" data-patrol-b-cell>
        <img src={level3Assets.bCellPatrol} alt="" draggable={false} />
        <SpeechBubble align="center" tone="success">
          {caught ? "抓到你了！我已被活化！开始分化！" : "巡逻中…"}
        </SpeechBubble>
      </div>
    </div>
  );
}
