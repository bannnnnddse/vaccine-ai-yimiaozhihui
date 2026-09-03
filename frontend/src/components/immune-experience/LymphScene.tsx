import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { TextType } from "../TextType";
import { BCellActivationSequence } from "./BCellActivationSequence";
import { CellEntity } from "./CellEntity";
import { ImmuneOutcomeScenes } from "./ImmuneOutcomeScenes";
import { IrisTransition } from "./IrisTransition";
import { MemoryRecallSequence } from "./MemoryRecallSequence";
import type {
  LevelThreeCell,
  LevelThreeCellId,
  LevelThreePhase,
} from "./levelThreeState";
import type { LevelThreeOpeningStage } from "./LevelThree";

export interface LymphSceneProps {
  cells: LevelThreeCell[];
  showCells: boolean;
  openingCaption: string | null;
  openingStage: LevelThreeOpeningStage;
  isOpeningCaptionTyping?: boolean;
  phase: LevelThreePhase;
  selectedCellId: LevelThreeCellId | null;
  revealedCellIds: LevelThreeCellId[];
  speech: string | null;
  speechTone: "info" | "warning" | "success";
  onSelectCell: (cellId: LevelThreeCellId) => void;
  onOpeningClick?: () => void;
  onContactContinue?: () => void;
  exitingActivationCaption?: "contact" | "helper-to-b" | null;
  onPatrolContinue?: () => void;
  onOutcomeScenesClick?: () => void;
  onAntibodySequenceClick?: () => void;
  onInterludeCaptionClick?: () => void;
  onInterludeCaptionComplete?: () => void;
}

export function LymphScene({
  cells,
  showCells,
  openingCaption,
  openingStage,
  isOpeningCaptionTyping = false,
  phase,
  selectedCellId,
  revealedCellIds,
  speech,
  speechTone,
  onSelectCell,
  onOpeningClick,
  onContactContinue,
  exitingActivationCaption = null,
  onPatrolContinue,
  onOutcomeScenesClick,
  onAntibodySequenceClick,
  onInterludeCaptionClick,
  onInterludeCaptionComplete,
}: LymphSceneProps) {
  const activationPhase = [
    "focus-b-cell",
    "t-cell-contact",
    "t-cell-contact-hold",
    "antigen-presentation",
    "antigen-presentation-hold",
    "b-cell-patrol-intro",
    "b-cell-patrol",
    "b-cell-patrol-caught",
    "differentiation",
    "plasma-ready",
    "antibody",
    "antibody-drift",
    "virus-entry",
    "antibody-binding",
    "neutralized",
  ].includes(phase);
  const finalePhase = [
    "outcome-transition",
    "outcome-scenes",
    "outcome-exit",
    "interlude-pause",
    "however-caption",
    "rechallenge-caption",
    "memory-recall",
    "memory-awakening",
    "memory-antibody-storm",
    "iris-focus",
    "iris-hold",
    "iris-close",
    "blackout",
  ].includes(phase);
  const memoryPhase = [
    "memory-recall",
    "memory-awakening",
    "memory-antibody-storm",
    "iris-focus",
    "iris-hold",
    "iris-close",
  ].includes(phase);
  const irisPhase = ["iris-focus", "iris-hold", "iris-close", "blackout"].includes(phase);
  const statusCaption = phase === "however-caption"
    ? "分化后的记忆B细胞会留在体内长期驻守"
    : phase === "rechallenge-caption"
      ? "当真正的病毒再次入侵时……"
      : null;
  const activationCaption = ["t-cell-contact", "t-cell-contact-hold"].includes(phase)
    ? "树突状细胞会将抗原标志物呈递给辅助性T细胞，\n并使其活化"
    : ["antigen-presentation", "antigen-presentation-hold"].includes(phase)
      ? "辅助性T细胞经树突状细胞激活后，迁移至B细胞区域为其提供第二活化信号"
      : null;
  const activationCaptionScene = ["t-cell-contact", "t-cell-contact-hold"].includes(phase)
    ? "contact"
    : ["antigen-presentation", "antigen-presentation-hold"].includes(phase)
      ? "helper-to-b"
      : null;
  return (
    <div
      className={`immune-level-three-lymph-scene is-${phase}`}
      style={{ backgroundImage: `url(${level3Assets.background})` }}
      onClick={() => {
        onOpeningClick?.();
        onContactContinue?.();
        onPatrolContinue?.();
        onOutcomeScenesClick?.();
        onAntibodySequenceClick?.();
        onInterludeCaptionClick?.();
      }}
      >
      <div className="immune-level-three-water-light" aria-hidden="true" />
      {activationCaption && activationCaptionScene && (
        <div
          key={activationCaptionScene}
          className={`immune-level-three-activation-caption is-${activationCaptionScene}${exitingActivationCaption === activationCaptionScene ? " is-exiting" : ""}`}
          role="status"
          aria-live="polite"
        >
          {activationCaption}
        </div>
      )}
      {openingCaption && (
        <div
          key={openingStage}
          className={`immune-level-three-opening-caption is-${openingStage}`}
          role="status"
          aria-live="polite"
        >
          {openingCaption}
          {isOpeningCaptionTyping && <span className="immune-level-three-opening-cursor" aria-hidden="true">|</span>}
        </div>
      )}
      {showCells && !activationPhase && !finalePhase && cells.map((cell) => {
        return (
          <CellEntity
            key={cell.id}
            cell={cell}
            asset={level3Assets[cell.assetKey]}
            selected={selectedCellId === cell.id}
            revealed={revealedCellIds.includes(cell.id)}
            withdrawing={false}
            activated={false}
            speech={selectedCellId === cell.id ? speech : null}
            speechTone={speechTone}
            onSelect={() => onSelectCell(cell.id)}
          />
        );
      })}
      {showCells && activationPhase && <BCellActivationSequence phase={phase} />}
      {(phase === "outcome-scenes" || phase === "outcome-exit") && (
        <ImmuneOutcomeScenes phase={phase} />
      )}
      {statusCaption && (
        <div
          className={`immune-level-three-opening-caption immune-level-three-status-caption is-${phase}`}
          role="status"
          aria-live="polite"
        >
          <TextType
            key={phase}
            text={statusCaption}
            typingSpeed={70}
            onComplete={onInterludeCaptionComplete}
          />
        </div>
      )}
      {memoryPhase && (
        <MemoryRecallSequence
          phase={phase as Extract<LevelThreePhase, "memory-recall" | "memory-awakening" | "memory-antibody-storm" | "iris-focus" | "iris-hold" | "iris-close">}
        />
      )}
      {irisPhase && (
        <IrisTransition
          phase={phase as Extract<LevelThreePhase, "iris-focus" | "iris-hold" | "iris-close" | "blackout">}
        />
      )}
    </div>
  );
}
