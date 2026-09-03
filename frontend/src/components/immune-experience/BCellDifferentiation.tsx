import type { CSSProperties } from "react";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { VirusNeutralization } from "./VirusNeutralization";
import type { LevelThreePhase, LevelThreePosition } from "./levelThreeState";

export interface BCellDifferentiationProps {
  phase: LevelThreePhase;
}

interface DifferentiatedCell {
  position: LevelThreePosition;
  fromX: string;
  fromY: string;
}

const MEMORY_CELLS: DifferentiatedCell[] = [
  { position: { x: 20, y: 28 }, fromX: "30vw", fromY: "22vh" },
  { position: { x: 50, y: 18 }, fromX: "0px", fromY: "32vh" },
  { position: { x: 80, y: 30 }, fromX: "-30vw", fromY: "20vh" },
];

const PLASMA_CELLS: DifferentiatedCell[] = [
  { position: { x: 16, y: 72 }, fromX: "34vw", fromY: "-22vh" },
  { position: { x: 34, y: 58 }, fromX: "16vw", fromY: "-8vh" },
  { position: { x: 50, y: 80 }, fromX: "0px", fromY: "-30vh" },
  { position: { x: 66, y: 58 }, fromX: "-16vw", fromY: "-8vh" },
  { position: { x: 84, y: 72 }, fromX: "-34vw", fromY: "-22vh" },
];

function differentiatedCellStyle(cell: DifferentiatedCell, index: number): CSSProperties {
  return {
    left: `${cell.position.x}%`,
    top: `${cell.position.y}%`,
    "--division-from-x": cell.fromX,
    "--division-from-y": cell.fromY,
    "--division-delay": `${index * 90}ms`,
  } as CSSProperties;
}

export function BCellDifferentiation({ phase }: BCellDifferentiationProps) {
  const finalePhases: LevelThreePhase[] = [
    "antibody",
    "antibody-drift",
    "virus-entry",
    "antibody-binding",
    "neutralized",
  ];
  const showMemoryCells = phase === "differentiation" || phase === "plasma-ready";
  const showPlasmaCells = phase === "differentiation" || phase === "plasma-ready" || phase === "antibody";
  return (
    <div className={`immune-b-cell-differentiation is-${phase}`}>
      {showMemoryCells && MEMORY_CELLS.map((cell, index) => (
        <div
          className={`immune-differentiated-cell is-memory${phase === "plasma-ready" ? " is-memory-withdrawing" : ""}`}
          data-memory-b-cell={index + 1}
          key={`memory-${index}`}
          style={differentiatedCellStyle(cell, index)}
        >
          <img src={level3Assets.memoryBCell} alt="记忆B细胞" draggable={false} />
        </div>
      ))}
      {showPlasmaCells && PLASMA_CELLS.map((cell, index) => (
        <div
          className="immune-differentiated-cell is-plasma"
          data-plasma-cell={index + 1}
          key={`plasma-${index}`}
          style={differentiatedCellStyle(cell, index + MEMORY_CELLS.length)}
        >
          <img src={level3Assets.plasmaCell} alt="浆细胞" draggable={false} />
        </div>
      ))}
      {finalePhases.includes(phase) && <VirusNeutralization phase={phase} />}
    </div>
  );
}
