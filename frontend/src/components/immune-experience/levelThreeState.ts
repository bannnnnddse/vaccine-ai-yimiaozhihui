export type LevelThreePhase =
  | "exploring"
  | "bCellFound"
  | "tCellFound"
  | "focus-b-cell"
  | "t-cell-contact"
  | "t-cell-contact-hold"
  | "antigen-presentation"
  | "antigen-presentation-hold"
  | "b-cell-patrol-intro"
  | "b-cell-patrol"
  | "b-cell-patrol-caught"
  | "differentiation"
  | "plasma-ready"
  | "antibody"
  | "antibody-drift"
  | "virus-entry"
  | "antibody-binding"
  | "neutralized"
  | "outcome-transition"
  | "outcome-scenes"
  | "outcome-exit"
  | "interlude-pause"
  | "however-caption"
  | "rechallenge-caption"
  | "memory-recall"
  | "memory-awakening"
  | "memory-antibody-storm"
  | "iris-focus"
  | "iris-hold"
  | "iris-close"
  | "blackout";

export type LevelThreeCellId =
  | "b-cell"
  | "helper-t-cell"
  | "dendritic-cell"
  | "macrophage"
  | "red-blood-cell";

export interface LevelThreePosition {
  x: number;
  y: number;
}

export interface LevelThreeCell {
  id: LevelThreeCellId;
  label: string;
  assetKey:
    | "explorationBCell"
    | "explorationHelperTCell"
    | "explorationDendriticCell"
    | "explorationMacrophage"
    | "explorationRedBloodCell";
  position: LevelThreePosition;
  drift: {
    x: number;
    y: number;
    rotate: number;
    duration: number;
    delay: number;
  };
  revealed: boolean;
  selected: boolean;
}

export interface LevelThreeState {
  phase: LevelThreePhase;
  selectedCellId: LevelThreeCellId | null;
  revealedCellIds: LevelThreeCellId[];
}

export type LevelThreeAction =
  | { type: "select-cell"; cellId: LevelThreeCellId }
  | { type: "dismiss-speech" }
  | { type: "complete-neutralization" }
  | { type: "advance-activation" };

export const INITIAL_LEVEL_THREE_STATE: LevelThreeState = {
  phase: "exploring",
  selectedCellId: null,
  revealedCellIds: [],
};

const CELL_BLUEPRINTS = [
  { id: "b-cell", label: "B淋巴细胞", assetKey: "explorationBCell" },
  { id: "helper-t-cell", label: "辅助性T细胞", assetKey: "explorationHelperTCell" },
  { id: "dendritic-cell", label: "树突状细胞", assetKey: "explorationDendriticCell" },
  { id: "macrophage", label: "巨噬细胞", assetKey: "explorationMacrophage" },
  { id: "red-blood-cell", label: "红细胞", assetKey: "explorationRedBloodCell" },
] as const;

const SAFE_POSITIONS: LevelThreePosition[] = [
  { x: 20, y: 24 },
  { x: 76, y: 22 },
  { x: 22, y: 72 },
  { x: 76, y: 72 },
];

function shuffledPositions(random: () => number): LevelThreePosition[] {
  const positions = SAFE_POSITIONS.map((position) => ({ ...position }));
  for (let index = positions.length - 1; index > 0; index -= 1) {
    const target = Math.floor(random() * (index + 1));
    [positions[index], positions[target]] = [positions[target], positions[index]];
  }
  return positions;
}

export function createLevelThreeCells(random: () => number = Math.random): LevelThreeCell[] {
  const positions = shuffledPositions(random);
  let outerPositionIndex = 0;
  return CELL_BLUEPRINTS.map((cell) => ({
    ...cell,
    position: cell.id === "b-cell" ? { x: 50, y: 50 } : positions[outerPositionIndex++],
    drift: {
      x: Math.round(8 + random() * 12),
      y: Math.round(10 + random() * 16),
      rotate: Math.round(3 + random() * 5),
      duration: Number((5 + random() * 3).toFixed(2)),
      delay: Number((-random() * 4).toFixed(2)),
    },
    revealed: false,
    selected: false,
  }));
}

function revealCell(state: LevelThreeState, cellId: LevelThreeCellId): LevelThreeCellId[] {
  return state.revealedCellIds.includes(cellId)
    ? state.revealedCellIds
    : [...state.revealedCellIds, cellId];
}

export function transitionLevelThree(
  state: LevelThreeState,
  action: LevelThreeAction,
): LevelThreeState {
  if (action.type === "dismiss-speech") return { ...state, selectedCellId: null };
  if (action.type === "complete-neutralization") {
    return ["virus-entry", "antibody-binding"].includes(state.phase)
      ? { ...state, phase: "neutralized", selectedCellId: null }
      : state;
  }
  if (action.type === "advance-activation") {
    const nextPhase: Partial<Record<LevelThreePhase, LevelThreePhase>> = {
      tCellFound: "focus-b-cell",
      "focus-b-cell": "t-cell-contact",
      "t-cell-contact": "t-cell-contact-hold",
      "t-cell-contact-hold": "antigen-presentation",
      "antigen-presentation": "antigen-presentation-hold",
      "antigen-presentation-hold": "b-cell-patrol-intro",
      "b-cell-patrol-intro": "b-cell-patrol",
      "b-cell-patrol": "b-cell-patrol-caught",
      "b-cell-patrol-caught": "differentiation",
      differentiation: "plasma-ready",
      "plasma-ready": "antibody",
      antibody: "antibody-drift",
      "antibody-drift": "virus-entry",
      "virus-entry": "antibody-binding",
      "antibody-binding": "neutralized",
      neutralized: "outcome-transition",
      "outcome-transition": "outcome-scenes",
      "outcome-scenes": "outcome-exit",
      "outcome-exit": "interlude-pause",
      "interlude-pause": "however-caption",
      "however-caption": "rechallenge-caption",
      "rechallenge-caption": "memory-recall",
      "memory-recall": "memory-awakening",
      "memory-awakening": "memory-antibody-storm",
      "memory-antibody-storm": "iris-focus",
      "iris-focus": "iris-hold",
      "iris-hold": "iris-close",
      "iris-close": "blackout",
    };
    const phase = nextPhase[state.phase];
    return phase ? { ...state, phase, selectedCellId: null } : state;
  }
  if (!["exploring", "bCellFound", "tCellFound"].includes(state.phase)) return state;

  const revealedCellIds = revealCell(state, action.cellId);
  if (action.cellId === "b-cell") {
    return state.phase === "tCellFound"
      ? state
      : { phase: "bCellFound", selectedCellId: action.cellId, revealedCellIds };
  }
  if (action.cellId === "helper-t-cell") {
    return { phase: "tCellFound", selectedCellId: action.cellId, revealedCellIds };
  }
  return { ...state, selectedCellId: action.cellId, revealedCellIds };
}
