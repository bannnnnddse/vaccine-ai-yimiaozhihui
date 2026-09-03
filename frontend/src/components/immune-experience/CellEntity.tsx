import type { CSSProperties } from "react";
import type { LevelThreeCell } from "./levelThreeState";
import { SpeechBubble } from "./SpeechBubble";

export interface CellEntityProps {
  cell: LevelThreeCell;
  asset: string;
  selected: boolean;
  revealed: boolean;
  withdrawing: boolean;
  activated: boolean;
  speech: string | null;
  speechTone?: "info" | "warning" | "success";
  onSelect: () => void;
}

function getSpeechAlignment(x: number): "left" | "center" | "right" {
  if (x < 32) return "left";
  if (x > 68) return "right";
  return "center";
}

export function CellEntity({
  cell,
  asset,
  selected,
  revealed,
  withdrawing,
  activated,
  speech,
  speechTone,
  onSelect,
}: CellEntityProps) {
  const style = {
    left: `${cell.position.x}%`,
    top: `${cell.position.y}%`,
    "--cell-float-x": `${cell.drift.x}px`,
    "--cell-float-y": `${cell.drift.y}px`,
    "--cell-float-rotate": `${cell.drift.rotate}deg`,
    "--cell-float-duration": `${cell.drift.duration}s`,
    "--cell-float-delay": `${cell.drift.delay}s`,
  } as CSSProperties;

  const className = [
    "immune-level-three-cell",
    selected ? "is-selected" : "",
    withdrawing ? "is-withdrawing" : "",
    activated ? "is-activated" : "",
    `is-${cell.id}`,
  ].filter(Boolean).join(" ");

  return (
    <button
      className={className}
      style={style}
      type="button"
      data-cell-id={cell.id}
      onClick={onSelect}
      disabled={withdrawing}
      aria-label={`观察${cell.label}`}
      aria-pressed={selected}
    >
      <span className="immune-level-three-cell__drift">
        <img src={asset} alt="" draggable={false} aria-hidden="true" />
      </span>
      {speech && (
        <SpeechBubble align={getSpeechAlignment(cell.position.x)} tone={speechTone}>
          {speech}
        </SpeechBubble>
      )}
    </button>
  );
}
