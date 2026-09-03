import { useCallback, useEffect, useRef, useState } from "react";
import {
  DIGITAL_HUMAN_CONFIG,
  type DigitalHumanTemplate,
} from "../config/digitalHumanConfig";
import type { ChatMode } from "../components/ChatInput";

export type DigitalHumanState = "idle" | "hinting" | "thinking" | "success" | "error";
export type DigitalHumanBubbleKind = "onboarding" | "idle" | "help" | "error";

export interface DigitalHumanBubble {
  id: string;
  kind: DigitalHumanBubbleKind;
  message: string;
  priority: number;
}

export interface ModeSessionState {
  welcomeShown: boolean;
  idleHintShown: boolean;
  meaningfulInteraction: boolean;
}

interface UseDigitalHumanInteractionOptions {
  mode: ChatMode;
  isBusy: boolean;
  modalOpen: boolean;
  pageActive: boolean;
}

const createModeSessionState = (): ModeSessionState => ({
  welcomeShown: false,
  idleHintShown: false,
  meaningfulInteraction: false,
});

export function createDigitalHumanModeSessionStore() {
  const sessions: Record<ChatMode, ModeSessionState> = {
    chat: createModeSessionState(),
    illustration: createModeSessionState(),
  };
  return {
    get: (mode: ChatMode) => sessions[mode],
    enter(mode: ChatMode): "welcome" | "idle-wait" | "none" {
      const session = sessions[mode];
      if (!session.welcomeShown) {
        session.welcomeShown = true;
        return "welcome";
      }
      return !session.meaningfulInteraction && !session.idleHintShown ? "idle-wait" : "none";
    },
    markMeaningful(mode: ChatMode) {
      sessions[mode].meaningfulInteraction = true;
    },
    markIdleHintShown(mode: ChatMode) {
      sessions[mode].idleHintShown = true;
    },
  };
}

export function useDigitalHumanInteraction({
  mode,
  isBusy,
  modalOpen,
  pageActive,
}: UseDigitalHumanInteractionOptions) {
  const [activeBubble, setActiveBubble] = useState<DigitalHumanBubble | null>(null);
  const [isPromptPanelOpen, setPromptPanelOpen] = useState(false);
  const [transientState, setTransientState] = useState<Exclude<DigitalHumanState, "thinking">>("idle");
  const sessionsRef = useRef(createDigitalHumanModeSessionStore());
  const currentModeRef = useRef(mode);
  const activeBubbleRef = useRef<DigitalHumanBubble | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const bubbleTimerRef = useRef<number | null>(null);
  const transientTimerRef = useRef<number | null>(null);
  const handledErrorsRef = useRef(new Set<string>());
  const handledSuccessRef = useRef(new Set<string>());
  const imageEditHintShownRef = useRef(false);
  const initializedModeRef = useRef<ChatMode | null>(null);
  const disposeTimerRef = useRef<number | null>(null);

  const clearTimer = (timerRef: { current: number | null }) => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
  };

  const clearIdleTimer = useCallback(() => clearTimer(idleTimerRef), []);
  const clearBubbleTimer = useCallback(() => clearTimer(bubbleTimerRef), []);
  const clearTransientTimer = useCallback(() => clearTimer(transientTimerRef), []);

  const replaceBubble = useCallback((bubble: DigitalHumanBubble | null) => {
    activeBubbleRef.current = bubble;
    setActiveBubble(bubble);
  }, []);

  const dismissBubble = useCallback(() => {
    clearBubbleTimer();
    replaceBubble(null);
    setTransientState("idle");
  }, [clearBubbleTimer, replaceBubble]);

  const showBubble = useCallback((
    bubble: DigitalHumanBubble,
    durationMs: number,
  ) => {
    if (activeBubbleRef.current && activeBubbleRef.current.priority > bubble.priority) return;
    clearBubbleTimer();
    replaceBubble(bubble);
    setTransientState(bubble.kind === "error" ? "error" : "hinting");
    bubbleTimerRef.current = window.setTimeout(() => {
      bubbleTimerRef.current = null;
      if (activeBubbleRef.current?.id !== bubble.id) return;
      replaceBubble(null);
      setTransientState("idle");
    }, durationMs);
  }, [clearBubbleTimer, replaceBubble]);

  const scheduleIdleHint = useCallback((targetMode: ChatMode) => {
    clearIdleTimer();
    const session = sessionsRef.current.get(targetMode);
    if (session.meaningfulInteraction || session.idleHintShown) return;
    idleTimerRef.current = window.setTimeout(() => {
      idleTimerRef.current = null;
      if (currentModeRef.current !== targetMode) return;
      const currentSession = sessionsRef.current.get(targetMode);
      if (currentSession.meaningfulInteraction || currentSession.idleHintShown) return;
      sessionsRef.current.markIdleHintShown(targetMode);
      showBubble({
        id: `${targetMode}-idle`,
        kind: "idle",
        message: targetMode === "chat"
          ? DIGITAL_HUMAN_CONFIG.bubbles.qaIdle
          : DIGITAL_HUMAN_CONFIG.bubbles.imageIdle,
        priority: 0,
      }, DIGITAL_HUMAN_CONFIG.timing.welcomeDurationMs);
    }, DIGITAL_HUMAN_CONFIG.timing.idleHintDelayMs);
  }, [clearIdleTimer, showBubble]);

  const startModeExperience = useCallback((targetMode: ChatMode, forceWelcome = false) => {
    const entry = sessionsRef.current.enter(targetMode);
    if (forceWelcome || entry === "welcome") {
      const bubbleId = `${targetMode}-welcome`;
      showBubble({
        id: bubbleId,
        kind: "onboarding",
        message: targetMode === "chat"
          ? DIGITAL_HUMAN_CONFIG.bubbles.qaWelcome
          : DIGITAL_HUMAN_CONFIG.bubbles.imageWelcome,
        priority: 1,
      }, DIGITAL_HUMAN_CONFIG.timing.welcomeDurationMs);
      clearIdleTimer();
      idleTimerRef.current = window.setTimeout(() => {
        idleTimerRef.current = null;
        if (currentModeRef.current !== targetMode) return;
        scheduleIdleHint(targetMode);
      }, DIGITAL_HUMAN_CONFIG.timing.welcomeDurationMs);
      return;
    }
    if (entry === "idle-wait") scheduleIdleHint(targetMode);
  }, [clearIdleTimer, scheduleIdleHint, showBubble]);

  const markMeaningfulInteraction = useCallback(() => {
    sessionsRef.current.markMeaningful(currentModeRef.current);
    clearIdleTimer();
    if (activeBubbleRef.current?.kind !== "error") dismissBubble();
  }, [clearIdleTimer, dismissBubble]);

  const closePromptPanel = useCallback(() => setPromptPanelOpen(false), []);

  const togglePromptPanel = useCallback(() => {
    markMeaningfulInteraction();
    dismissBubble();
    setPromptPanelOpen((open) => !open);
  }, [dismissBubble, markMeaningfulInteraction]);

  const notifyError = useCallback((key: string, targetMode: ChatMode) => {
    if (handledErrorsRef.current.has(key)) return;
    handledErrorsRef.current.add(key);
    clearIdleTimer();
    if (!pageActive || modalOpen || isPromptPanelOpen) return;
    showBubble({
      id: `error-${key}`,
      kind: "error",
      message: targetMode === "chat"
        ? DIGITAL_HUMAN_CONFIG.bubbles.qaError
        : DIGITAL_HUMAN_CONFIG.bubbles.imageError,
      priority: 2,
    }, DIGITAL_HUMAN_CONFIG.timing.errorDurationMs);
  }, [clearIdleTimer, isPromptPanelOpen, modalOpen, pageActive, showBubble]);

  const notifySuccess = useCallback((key: string) => {
    if (handledSuccessRef.current.has(key)) return;
    handledSuccessRef.current.add(key);
    clearTransientTimer();
    setTransientState("success");
    transientTimerRef.current = window.setTimeout(() => {
      transientTimerRef.current = null;
      setTransientState("idle");
    }, DIGITAL_HUMAN_CONFIG.timing.successDurationMs);
  }, [clearTransientTimer]);

  const notifyImageEditHint = useCallback(() => {
    if (imageEditHintShownRef.current) return;
    imageEditHintShownRef.current = true;
    if (!pageActive || modalOpen || isPromptPanelOpen) return;
    showBubble({
      id: "image-edit-hint",
      kind: "help",
      message: DIGITAL_HUMAN_CONFIG.bubbles.imageEditHint,
      priority: 2,
    }, DIGITAL_HUMAN_CONFIG.timing.editHintDurationMs);
  }, [isPromptPanelOpen, modalOpen, pageActive, showBubble]);

  useEffect(() => {
    currentModeRef.current = mode;
    const modeChanged = initializedModeRef.current !== mode;
    if (modeChanged) {
      initializedModeRef.current = mode;
      clearIdleTimer();
      dismissBubble();
      setPromptPanelOpen(false);
    }
    if (pageActive && !isBusy && !modalOpen && !activeBubbleRef.current) {
      startModeExperience(mode, modeChanged);
    }
  }, [clearIdleTimer, dismissBubble, isBusy, modalOpen, mode, pageActive, startModeExperience]);

  useEffect(() => {
    if (!pageActive || modalOpen || isBusy || isPromptPanelOpen) {
      clearIdleTimer();
      if (activeBubbleRef.current && activeBubbleRef.current.priority < 2) dismissBubble();
      return;
    }
    if (!activeBubbleRef.current) startModeExperience(mode);
  }, [clearIdleTimer, dismissBubble, isBusy, isPromptPanelOpen, modalOpen, mode, pageActive, startModeExperience]);

  useEffect(() => {
    if (disposeTimerRef.current !== null) window.clearTimeout(disposeTimerRef.current);
    disposeTimerRef.current = null;
    return () => {
      disposeTimerRef.current = window.setTimeout(() => {
        clearIdleTimer();
        clearBubbleTimer();
        clearTransientTimer();
      }, 0);
    };
  }, [clearBubbleTimer, clearIdleTimer, clearTransientTimer]);

  const templates: readonly DigitalHumanTemplate[] = mode === "chat"
    ? DIGITAL_HUMAN_CONFIG.qaTemplates
    : DIGITAL_HUMAN_CONFIG.imageTemplates;

  return {
    state: isBusy ? "thinking" as const : transientState,
    activeBubble,
    isPromptPanelOpen,
    templates,
    panelTitle: mode === "chat"
      ? DIGITAL_HUMAN_CONFIG.panelTitles.qa
      : DIGITAL_HUMAN_CONFIG.panelTitles.image,
    markMeaningfulInteraction,
    togglePromptPanel,
    closePromptPanel,
    notifyError,
    notifySuccess,
    notifyImageEditHint,
  };
}
