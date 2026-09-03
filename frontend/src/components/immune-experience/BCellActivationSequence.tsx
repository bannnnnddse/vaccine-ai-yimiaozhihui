import type { LevelThreePhase } from "./levelThreeState";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { BCellDifferentiation } from "./BCellDifferentiation";
import { SpeechBubble } from "./SpeechBubble";
import { BCellPatrol } from "./BCellPatrol";

export interface BCellActivationSequenceProps {
  phase: LevelThreePhase;
}

function HelperTCellSprite() {
  return (
    <span className="immune-helper-t-cell" aria-hidden="true">
      <img
        className="immune-helper-t-cell__body"
        src={level3Assets.helperTCell}
        alt=""
        draggable={false}
      />
      <img
        className="immune-helper-t-cell__label"
        src={level3Assets.helperTCellLabel}
        alt=""
        draggable={false}
      />
    </span>
  );
}

export function BCellActivationSequence({ phase }: BCellActivationSequenceProps) {
  if (["b-cell-patrol-intro", "b-cell-patrol", "b-cell-patrol-caught"].includes(phase)) {
    return <BCellPatrol phase={phase as "b-cell-patrol-intro" | "b-cell-patrol" | "b-cell-patrol-caught"} />;
  }
  if (
    [
      "differentiation",
      "plasma-ready",
      "antibody",
      "antibody-drift",
      "virus-entry",
      "antibody-binding",
      "neutralized",
    ].includes(phase)
  ) {
    return <BCellDifferentiation phase={phase} />;
  }

  return (
    <div className={`immune-b-cell-activation is-${phase}`}>
      {(["focus-b-cell", "t-cell-contact", "t-cell-contact-hold"] as const).includes(
        phase as "focus-b-cell" | "t-cell-contact" | "t-cell-contact-hold",
      ) && (
        <div className="immune-b-cell-activation__helper-focus" data-helper-t-focus>
          <HelperTCellSprite />
        </div>
      )}
      {(["t-cell-contact", "t-cell-contact-hold"] as const).includes(
        phase as "t-cell-contact" | "t-cell-contact-hold",
      ) && (
        <img
          className="immune-b-cell-activation__presenter"
          data-antigen-presenter
          src={level3Assets.antigenPresentingCell}
          alt=""
          draggable={false}
        />
      )}
      {(["antigen-presentation", "antigen-presentation-hold"] as const).includes(
        phase as "antigen-presentation" | "antigen-presentation-hold",
      ) && (
        <>
          <div className="immune-b-cell-activation__b-cell" data-activation-b-cell>
            <img src={level3Assets.bCell} alt="" draggable={false} />
            <SpeechBubble tone="success" align="center">收到</SpeechBubble>
          </div>
          <div className="immune-b-cell-activation__helper-to-b" data-helper-t-contact>
            <HelperTCellSprite />
          </div>
        </>
      )}
    </div>
  );
}
