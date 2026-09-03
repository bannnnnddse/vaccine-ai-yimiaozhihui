import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { LymphScene } from "./LymphScene";
import { useReducedMotion } from "./useReducedMotion";
import {
  INITIAL_LEVEL_THREE_STATE,
  createLevelThreeCells,
  transitionLevelThree,
  type LevelThreeCellId,
  type LevelThreePhase,
  type LevelThreeState,
} from "./levelThreeState";

export interface LevelThreeProps {
  onEnter?: () => void;
}

export type LevelThreeOpeningStage = "context" | "arrival" | "prompt" | "ready";

const OPENING_TYPING_SPEED_MS = 85;
export const OPENING_HOLD_DURATION_MS = 30_000;
export const ACTIVATION_CAPTION_SCENE_DURATION_MS = 8_000;
export const ACTIVATION_CAPTION_FADE_DURATION_MS = 400;
export const INTERLUDE_CAPTION_HOLD_DURATION_MS = 30_000;

type ActivationCaptionScene = "contact" | "helper-to-b";

function getActivationCaptionScene(phase: LevelThreePhase): ActivationCaptionScene | null {
  if (["t-cell-contact", "t-cell-contact-hold"].includes(phase)) return "contact";
  if (["antigen-presentation", "antigen-presentation-hold"].includes(phase)) return "helper-to-b";
  return null;
}

export function getLevelThreeOpeningStage(elapsedMs: number): LevelThreeOpeningStage {
  if (elapsedMs < 4000) return "context";
  if (elapsedMs < 7000) return "arrival";
  if (elapsedMs < 10000) return "prompt";
  return "ready";
}

export function getLevelThreeActivationDuration(phase: LevelThreePhase): number | null {
  const durations: Partial<Record<LevelThreePhase, number>> = {
    tCellFound: 1400,
    "focus-b-cell": 700,
    "t-cell-contact": 1800,
    "t-cell-contact-hold": undefined,
    "antigen-presentation": 1600,
    "antigen-presentation-hold": undefined,
    "b-cell-patrol-intro": 700,
    "b-cell-patrol": 4300,
    differentiation: 3000,
    "plasma-ready": 400,
    antibody: 4500,
    "antibody-drift": undefined,
    "virus-entry": 3000,
    "antibody-binding": 2600,
    neutralized: undefined,
    "outcome-transition": 900,
    "outcome-scenes": 8000,
    "outcome-exit": 1200,
    "interlude-pause": 500,
    "however-caption": undefined,
    "rechallenge-caption": undefined,
    "memory-recall": 3600,
    "memory-awakening": 600,
    "memory-antibody-storm": 4500,
    "iris-focus": 1400,
    "iris-hold": 1000,
    "iris-close": 650,
  };
  return durations[phase] ?? null;
}

const ANTIBODY_RESPONSE_PHASES: LevelThreePhase[] = [
  "antibody",
  "antibody-drift",
  "virus-entry",
  "antibody-binding",
];

const OUTCOME_PHASES: LevelThreePhase[] = [
  "outcome-transition",
  "outcome-scenes",
  "outcome-exit",
  "interlude-pause",
  "however-caption",
  "rechallenge-caption",
];

const RECALL_PHASES: LevelThreePhase[] = [
  "memory-recall",
  "memory-awakening",
  "memory-antibody-storm",
  "iris-focus",
  "iris-hold",
  "iris-close",
];

export function getLevelThreeMission(phase: LevelThreePhase): string | null {
  if (phase === "blackout") return null;
  if (OUTCOME_PHASES.includes(phase)) return "抗体标记后，病毒还会经历什么？";
  if (RECALL_PHASES.includes(phase)) return "记忆 B 细胞正在快速启动二次应答……";
  if (phase === "neutralized") return "免疫应答完成：抗体已识别并包裹病毒";
  if (ANTIBODY_RESPONSE_PHASES.includes(phase)) {
    return "识别成功：B细胞在辅助性T细胞帮助下建立免疫应答";
  }
  return "任务：识别免疫细胞，找到能帮助B细胞的伙伴";
}

export function shouldShowLevelThreeSuccess(phase: LevelThreePhase): boolean {
  return [...ANTIBODY_RESPONSE_PHASES, "neutralized"].includes(phase);
}

export function canAdvanceInterludeCaption(phase: LevelThreePhase): boolean {
  return phase === "however-caption" || phase === "rechallenge-caption";
}

const DISTRACTOR_CELLS: LevelThreeCellId[] = ["dendritic-cell", "macrophage", "red-blood-cell"];

function getSpeech(state: LevelThreeState): {
  text: string | null;
  tone: "info" | "warning" | "success";
} {
  switch (state.selectedCellId) {
    case "b-cell":
      return { text: "我目前还未被活化，\n你找我没有用。", tone: "info" };
    case "helper-t-cell":
      return { text: "这事儿你找我就对了。", tone: "success" };
    case "dendritic-cell":
      return { text: "我是树突状细胞，负责捕获并呈递抗原。\n这一关，请继续寻找B细胞和辅助性T细胞。", tone: "info" };
    case "macrophage":
      return { text: "错误！我是巨噬细胞！\n你找我没有用。", tone: "warning" };
    case "red-blood-cell":
      return { text: "我是红细胞！我只负责运输氧气，\n不抓病毒！", tone: "warning" };
    default:
      return { text: null, tone: "info" };
  }
}

export function LevelThree({ onEnter }: LevelThreeProps) {
  const [state, dispatch] = useReducer(transitionLevelThree, INITIAL_LEVEL_THREE_STATE);
  const [openingStage, setOpeningStage] = useState<LevelThreeOpeningStage>("context");
  const [openingCaption, setOpeningCaption] = useState("");
  const [isOpeningWaiting, setIsOpeningWaiting] = useState(false);
  const [exitingActivationCaption, setExitingActivationCaption] = useState<ActivationCaptionScene | null>(null);
  const [completedInterludeCaptionPhase, setCompletedInterludeCaptionPhase] = useState<LevelThreePhase | null>(null);
  const [cells] = useState(() => createLevelThreeCells());
  const prefersReducedMotion = useReducedMotion();
  const notifiedRef = useRef(false);
  const speech = getSpeech(state);
  const showSuccess = shouldShowLevelThreeSuccess(state.phase);

  useEffect(() => {
    if (notifiedRef.current) return;
    notifiedRef.current = true;
    onEnter?.();
  }, [onEnter]);

  const advanceOpening = useCallback(() => {
    if (!isOpeningWaiting) return;
    setOpeningStage((stage) => {
      const index = ["context", "arrival", "prompt"].indexOf(stage);
      return index === -1 || index === 2
        ? "ready"
        : ["context", "arrival", "prompt"][index + 1] as LevelThreeOpeningStage;
    });
  }, [isOpeningWaiting]);

  useEffect(() => {
    if (openingStage === "ready") return;

    const captions = [
      "你被树突状细胞吞噬了，\n他从你身上提取出了抗原标志物并呈递",
      "呈递后他会来到淋巴组织内寻求帮助",
      "淋巴组织内存在着大量免疫细胞，看看谁能提供帮助？",
    ];
    const captionIndex = ["context", "arrival", "prompt"].indexOf(openingStage);
    const caption = captions[captionIndex];
    let typingTimer: number | undefined;
    let holdTimer: number | undefined;
    let characterIndex = 0;

    const advanceAfterHold = () => {
      setOpeningStage((stage) => {
        const index = ["context", "arrival", "prompt"].indexOf(stage);
        return index === 2 ? "ready" : ["context", "arrival", "prompt"][index + 1] as LevelThreeOpeningStage;
      });
    };
    const beginHold = () => {
      setIsOpeningWaiting(true);
      holdTimer = window.setTimeout(advanceAfterHold, OPENING_HOLD_DURATION_MS);
    };

    setOpeningCaption(prefersReducedMotion ? caption : "");
    setIsOpeningWaiting(false);
    if (prefersReducedMotion) {
      beginHold();
    } else {
      const typeNextCharacter = () => {
        characterIndex += 1;
        setOpeningCaption(caption.slice(0, characterIndex));
        if (characterIndex < caption.length) typingTimer = window.setTimeout(typeNextCharacter, OPENING_TYPING_SPEED_MS);
        else beginHold();
      };
      typingTimer = window.setTimeout(typeNextCharacter, OPENING_TYPING_SPEED_MS);
    }

    return () => {
      if (typingTimer !== undefined) window.clearTimeout(typingTimer);
      if (holdTimer !== undefined) window.clearTimeout(holdTimer);
    };
  }, [openingStage, prefersReducedMotion]);

  useEffect(() => {
    if (
      prefersReducedMotion
      && ["t-cell-contact", "antigen-presentation"].includes(state.phase)
    ) {
      dispatch({ type: "advance-activation" });
      return;
    }
    if (exitingActivationCaption && getActivationCaptionScene(state.phase)) return;
    const duration = getLevelThreeActivationDuration(state.phase);
    if (duration === null) return;
    const timeout = window.setTimeout(() => dispatch({ type: "advance-activation" }), duration);
    return () => window.clearTimeout(timeout);
  }, [exitingActivationCaption, state.phase, prefersReducedMotion]);

  useEffect(() => {
    const scene = getActivationCaptionScene(state.phase);
    if (exitingActivationCaption !== null && scene !== exitingActivationCaption) {
      setExitingActivationCaption(null);
    }
  }, [exitingActivationCaption, state.phase]);

  useEffect(() => {
    if (!["t-cell-contact-hold", "antigen-presentation-hold"].includes(state.phase)) return;
    if (exitingActivationCaption) return;

    const playbackDuration = state.phase === "t-cell-contact-hold" ? 1_800 : 1_600;
    const fadeDuration = prefersReducedMotion ? 0 : ACTIVATION_CAPTION_FADE_DURATION_MS;
    const delay = prefersReducedMotion
      ? ACTIVATION_CAPTION_SCENE_DURATION_MS
      : ACTIVATION_CAPTION_SCENE_DURATION_MS - playbackDuration - fadeDuration;
    const timeout = window.setTimeout(() => {
      setExitingActivationCaption(getActivationCaptionScene(state.phase));
    }, delay);
    return () => window.clearTimeout(timeout);
  }, [exitingActivationCaption, prefersReducedMotion, state.phase]);

  useEffect(() => {
    if (!exitingActivationCaption) return;
    if (getActivationCaptionScene(state.phase) !== exitingActivationCaption) return;

    const phaseAtExit = state.phase;
    const advanceAfterExit = () => {
      dispatch({ type: "advance-activation" });
      if (phaseAtExit === "t-cell-contact" || phaseAtExit === "antigen-presentation") {
        dispatch({ type: "advance-activation" });
      }
    };
    if (prefersReducedMotion) {
      advanceAfterExit();
      return;
    }
    const timeout = window.setTimeout(advanceAfterExit, ACTIVATION_CAPTION_FADE_DURATION_MS);
    return () => window.clearTimeout(timeout);
  }, [exitingActivationCaption, prefersReducedMotion, state.phase]);

  useEffect(() => {
    if (!state.selectedCellId || !DISTRACTOR_CELLS.includes(state.selectedCellId)) return;
    const timeout = window.setTimeout(() => dispatch({ type: "dismiss-speech" }), 2800);
    return () => window.clearTimeout(timeout);
  }, [state.selectedCellId]);

  const advancePatrol = useCallback(() => {
    if (state.phase === "b-cell-patrol-caught") dispatch({ type: "advance-activation" });
  }, [state.phase]);

  const advanceContact = useCallback(() => {
    const scene = getActivationCaptionScene(state.phase);
    if (scene && !exitingActivationCaption) setExitingActivationCaption(scene);
  }, [exitingActivationCaption, state.phase]);

  const advanceOutcomeScenes = useCallback(() => {
    if (state.phase === "outcome-scenes") dispatch({ type: "advance-activation" });
  }, [state.phase]);

  const advanceAntibodySequence = useCallback(() => {
    if (["antibody", "antibody-drift", "neutralized"].includes(state.phase)) {
      dispatch({ type: "advance-activation" });
    } else if (["virus-entry", "antibody-binding"].includes(state.phase)) {
      dispatch({ type: "complete-neutralization" });
    }
  }, [state.phase]);

  const advanceInterludeCaption = useCallback(() => {
    if (
      canAdvanceInterludeCaption(state.phase)
      && completedInterludeCaptionPhase === state.phase
    ) {
      dispatch({ type: "advance-activation" });
    }
  }, [completedInterludeCaptionPhase, state.phase]);

  const completeInterludeCaption = useCallback(() => {
    if (canAdvanceInterludeCaption(state.phase)) {
      setCompletedInterludeCaptionPhase(state.phase);
    }
  }, [state.phase]);

  useEffect(() => {
    if (completedInterludeCaptionPhase !== state.phase) return;
    if (!canAdvanceInterludeCaption(state.phase)) return;

    const timeout = window.setTimeout(
      () => dispatch({ type: "advance-activation" }),
      INTERLUDE_CAPTION_HOLD_DURATION_MS,
    );
    return () => window.clearTimeout(timeout);
  }, [completedInterludeCaptionPhase, state.phase]);

  useEffect(() => {
    if (typeof window.addEventListener !== "function") return;
    const advance = () => {
      if (openingStage !== "ready") {
        setOpeningStage("ready");
        return;
      }
      if (state.phase === "exploring") {
        dispatch({ type: "select-cell", cellId: "b-cell" });
      } else if (state.phase === "bCellFound") {
        dispatch({ type: "select-cell", cellId: "helper-t-cell" });
      } else {
        dispatch({ type: "advance-activation" });
      }
    };
    window.addEventListener("immune-experience:developer-advance", advance);
    return () => window.removeEventListener("immune-experience:developer-advance", advance);
  }, [openingStage, state.phase]);

  return (
    <section className="immune-level-three" aria-label="淋巴液免疫识别">
      <LymphScene
        cells={cells}
        showCells={openingStage === "ready"}
        openingCaption={openingStage === "ready" ? null : openingCaption}
        openingStage={openingStage}
        isOpeningCaptionTyping={!prefersReducedMotion && !isOpeningWaiting}
        phase={state.phase}
        selectedCellId={state.selectedCellId}
        revealedCellIds={state.revealedCellIds}
        speech={speech.text}
        speechTone={speech.tone}
        onSelectCell={(cellId) => dispatch({ type: "select-cell", cellId })}
        onOpeningClick={advanceOpening}
        onContactContinue={advanceContact}
        exitingActivationCaption={exitingActivationCaption}
        onPatrolContinue={advancePatrol}
        onOutcomeScenesClick={advanceOutcomeScenes}
        onAntibodySequenceClick={advanceAntibodySequence}
        onInterludeCaptionClick={advanceInterludeCaption}
        onInterludeCaptionComplete={completeInterludeCaption}
      />
      {(["antibody", "antibody-drift", "virus-entry", "antibody-binding", "neutralized"] as LevelThreePhase[]).includes(state.phase) && (
        <p key={state.phase} className={`immune-antibody-caption is-${state.phase}`} role="status">
          {state.phase === "neutralized"
            ? "抗体已黏附病毒"
            : ["virus-entry", "antibody-binding"].includes(state.phase)
              ? "抗体正在黏附病毒"
              : "抗体正在大量生成"}
        </p>
      )}
    </section>
  );
}
