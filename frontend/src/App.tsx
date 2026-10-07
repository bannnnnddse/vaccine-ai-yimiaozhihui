import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { DigitalHumanTemplate } from "./config/digitalHumanConfig";
import { AdminEntryLink } from "./components/AdminEntryLink";
import { AssistantContextPanel } from "./components/AssistantContextPanel";
import type { AppPage } from "./components/CardNav";
import { type ChatMode } from "./components/ChatInput";
import {
  type ChatMessageData,
  type ImageResultChatMessage,
  type ImageStatusChatMessage,
} from "./components/ChatMessage";
import { ChatPanel } from "./components/ChatPanel";
import { ImageHistoryModal } from "./components/ImageHistoryModal";
import { InteractiveDemoModal } from "./components/InteractiveDemoModal";
import { InteractiveExperiencePicker } from "./components/InteractiveExperiencePicker";
import { VirusSpreadingSimulation } from "./components/virus-spreading/VirusSpreadingSimulation";
import { VideoGenerationModal } from "./components/VideoGenerationModal";
import { WorkspaceNavigation } from "./components/WorkspaceNavigation";
import { knowledgeTopics } from "./data/questions";
import {
  acceptImageJob,
  cancelImageJob,
  ChatRequestError,
  createImageJob,
  editImageJob,
  generateChatAnswer,
  generateChatAnswerStream,
  generateConversationTitle,
  getImageJob,
  ImageJobRequestError,
  type ImageJob,
  type ImageJobStage,
  type ImageProcessEvent,
  type KnowledgeSource,
  type NormalizedBBox,
  restorePreviousImageJob,
} from "./services/generationService";
import {
  clearChatSessionId,
} from "./services/chatSession";
import { createTypingFrames } from "./utils/typewriter";
import { preloadVirusDiaryAssets } from "./utils/preloadVirusDiaryAssets";
import { useDigitalHumanInteraction } from "./hooks/useDigitalHumanInteraction";
import {
  IMAGE_HISTORY_STORAGE_KEY,
  loadImageHistory,
  saveImageHistoryEntry,
} from "./services/imageHistory";
import {
  createConversationId,
  fallbackConversationTitle,
  loadConversations,
  persistConversations,
  type StoredConversation,
} from "./services/conversationHistory";

export type { ChatMode } from "./components/ChatInput";
export type { ChatMessageData, MessageKind } from "./components/ChatMessage";

const NORMAL_POLL_DELAY = 1_500;
const BACKGROUND_POLL_DELAY = 5_000;
const POLL_BACKOFF_DELAYS = [1_500, 3_000, 5_000] as const;
const KnowledgeGraphViewer = lazy(() => import("./components/knowledge-graph/KnowledgeGraphViewer"));

// 本地答辩演示：旧流感图解 + “突破性感染”问答/图解集中放置，结束后可整块删除。
const LOCAL_SHOWCASE_DEMOS = {
  fluVaccineIllustration: {
    prompt: "流感疫苗有什么作用，请给我图解",
    imageUrl: "/demo-flu-vaccine.png",
    jobId: "local-demo-flu-vaccine",
    imageId: "local-demo-flu-vaccine-v0",
    traceId: "local-demo-flu-vaccine-trace",
    understandingDetail: "识别到主题是流感疫苗的作用，准备以“认识—准备—应对”的顺序讲清楚免疫保护过程。",
    structureDetail: "突出疫苗帮助免疫系统提前认识流感病毒、形成抗体和免疫记忆；同时保留“不能保证百分之百不感染”的边界说明。",
  },
  breakthroughInfection: {
    prompt: "打了疫苗为什么还会感染？那疫苗到底有没有用？",
    answer: "疫苗不是一堵保证病毒永远进不来的墙，更像是提前交给身体的一张“通缉令”，也是一次安全的免疫演习。接种后，免疫系统会认识病毒身上的特征，产生抗体，并留下具有记忆能力的免疫细胞。等真正的病毒来临时，身体就不必从头摸索，而能更快识别它、调动防线，在病毒造成更大伤害之前展开反击。\n\n当然，疫苗并不能保证每个人、每一次都不被感染，因为免疫反应会随时间变化，病毒也可能发生变异。但“仍有可能感染”并不等于“疫苗没有作用”。它更重要的价值，是降低感染后的严重程度，减少重症和死亡的风险。我们接种疫苗，不只是为自己多穿一层防护衣，也是在为老人、孩子和免疫力较弱的人，多撑起一把伞。",
    imageUrl: "/demo-vaccine-breakthrough-infection.png",
    jobId: "local-demo-vaccine-breakthrough-infection",
    imageId: "local-demo-vaccine-breakthrough-infection-v0",
    traceId: "local-demo-vaccine-breakthrough-infection-trace",
    understandingDetail: "识别到用户想了解接种后仍可能感染的原因，以及疫苗是否仍有保护价值。",
    structureDetail: "用“提前识别、快速反击、减轻伤害”的因果链解释疫苗不保证阻断每次感染，但仍能发挥保护作用。",
  },
} as const;

type LocalIllustrationDemo = typeof LOCAL_SHOWCASE_DEMOS.fluVaccineIllustration
  | typeof LOCAL_SHOWCASE_DEMOS.breakthroughInfection;

const progressCopy: Partial<Record<ImageJobStage, string>> = {
  queued: "任务排队中…",
  rewriting_prompt: "正在优化生成提示词…",
  generating: "正在生成科学图解…",
  critic_review_1: "AI 正在审核首次结果…",
  auto_revising: "AI 正在自动修订一次…",
  guard_check: "正在检查编辑是否影响框外区域…",
  critic_review_2: "AI 正在复审自动修订结果…",
  editing_with_bbox: "正在执行区域编辑…",
  critic_review_final: "AI 正在审核局部修改结果…",
};

const runningImageStages: ImageJobStage[] = ["queued", "rewriting_prompt", "generating", "critic_review_1", "auto_revising", "guard_check", "critic_review_2", "editing_with_bbox", "critic_review_final"];

interface ActiveImageJob {
  jobId: string | null;
  requestToken: string;
  prompt: string;
  messageId: string;
  sourceMessageId?: string;
}

interface PendingImageResult {
  job: ImageJob;
  requestToken: string;
  prompt: string;
}

type CancelReason = "user" | "mode-switch" | "unmount";

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function finishLocalTrace(
  events: ImageProcessEvent[] | undefined, title: string, detail?: string,
): ImageProcessEvent[] {
  const now = new Date().toISOString();
  const currentEvents = events ?? [];
  const settled = currentEvents.map((event, index) => index === currentEvents.length - 1 && event.status === "running"
    ? { ...event, status: "warning" as const }
    : event);
  return [...settled, {
    id: `client-terminal-${now}-${settled.length}`,
    stage: "warning",
    title,
    ...(detail ? { detail } : {}),
    status: "warning",
    createdAt: now,
  }];
}

function normalizeDemoPrompt(prompt: string): string {
  return prompt.trim().replace(/\s+/g, "");
}

function findLocalIllustrationDemo(prompt: string): LocalIllustrationDemo | undefined {
  const normalizedPrompt = normalizeDemoPrompt(prompt);
  return Object.values(LOCAL_SHOWCASE_DEMOS).find((demo) => (
    "imageUrl" in demo && normalizeDemoPrompt(demo.prompt) === normalizedPrompt
  ));
}

function getLocalChatDemoAnswer(prompt: string): string | undefined {
  const demo = LOCAL_SHOWCASE_DEMOS.breakthroughInfection;
  return normalizeDemoPrompt(prompt) === normalizeDemoPrompt(demo.prompt) ? demo.answer : undefined;
}

function createLocalIllustrationDemoJob(demo: LocalIllustrationDemo): ImageJob {
  const now = new Date().toISOString();
  return {
    jobId: demo.jobId,
    stage: "awaiting_human_feedback",
    imageUrl: demo.imageUrl,
    imageId: demo.imageId,
    autoRevisionCount: 0,
    revisionOrigin: "initial",
    traceId: demo.traceId,
    traceEvents: [
      {
        id: `${demo.jobId}-understanding`,
        stage: "understanding",
        title: "正在理解图解需求",
        detail: demo.understandingDetail,
        status: "completed",
        createdAt: now,
      },
      {
        id: `${demo.jobId}-structure`,
        stage: "prompt_rewrite",
        title: "正在组织科学表达",
        detail: demo.structureDetail,
        status: "completed",
        createdAt: now,
      },
      {
        id: `${demo.jobId}-completed`,
        stage: "completed",
        title: "图解已准备完成",
        detail: "已生成本地演示图解，你可以接受结果，或继续框选区域提出修改建议。",
        status: "completed",
        createdAt: now,
      },
    ],
  };
}

export function App() {
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [conversations, setConversations] = useState<StoredConversation[]>(() => loadConversations());
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<ChatMode>("chat");
  const [imageHistory, setImageHistory] = useState(() => loadImageHistory());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [selectedQuestionId, setSelectedQuestionId] = useState("");
  const [isAnswering, setIsAnswering] = useState(false);
  const [isTypingAnswer, setIsTypingAnswer] = useState(false);
  const [chatProgress, setChatProgress] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<AppPage>(() =>
    typeof window !== "undefined" && window.location?.hash === "#graph" ? "graph" : "answer"
  );
  const typingTimer = useRef<number | null>(null);
  const typingResolveRef = useRef<(() => void) | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const requestSequenceRef = useRef(0);
  const chatRequestSequenceRef = useRef(0);
  const mountedRef = useRef(true);
  const activeImageJobRef = useRef<ActiveImageJob | null>(null);
  const pendingCancellationRef = useRef(new Map<string, string>());
  const createAbortRef = useRef<AbortController | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const pollAbortRef = useRef<AbortController | null>(null);
  const pendingImageResultsRef = useRef(new Map<string, PendingImageResult>());
  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  const activeConversationIdRef = useRef<string | null>(null);
  const activeSessionIdRef = useRef<string | null>(null);
  const suppressConversationPersistenceRef = useRef(false);
  const titleRequestIdsRef = useRef(new Set(
    conversations
      .filter((conversation) => conversation.titleStatus === "generated")
      .map((conversation) => conversation.id),
  ));

  const currentTopic = useMemo(
    () => messages.filter((message) => message.role === "user" && message.kind === "text").at(-1)?.content
      || "请先选择或输入一个问题",
    [messages],
  );

  const digitalHumanBusy = isAnswering || isTypingAnswer || messages.some((message) => (
    (message.kind === "image-status" || message.kind === "image-result")
    && ((message.kind === "image-status" && message.isRevealingTrace)
      || !["completed", "awaiting_human_feedback", "failed", "cancelled"].includes(message.stage))
  ));
  const digitalHuman = useDigitalHumanInteraction({
    mode,
    isBusy: digitalHumanBusy,
    modalOpen: historyOpen,
    pageActive: activePage === "answer",
  });

  const settleDigitalHumanForImage = (job: ImageJob) => {
    digitalHuman.notifySuccess(`image-${job.jobId}-${job.stage}`);
    if (job.stage === "awaiting_human_feedback") digitalHuman.notifyImageEditHint();
  };

  const persistConversationMessages = (
    nextMessages: ChatMessageData[],
    options: { touch?: boolean; modeOverride?: ChatMode } = {},
  ) => {
    const firstUserMessage = nextMessages.find((message) => (
      message.role === "user" && message.kind === "text" && message.content.trim()
    ));
    if (!firstUserMessage || firstUserMessage.kind !== "text") return;

    const now = Date.now();
    let conversationId = activeConversationIdRef.current;
    if (!conversationId) {
      conversationId = createConversationId();
      activeConversationIdRef.current = conversationId;
      setActiveConversationId(conversationId);
    }
    const stableMessages = nextMessages.map((message) => (
      message.kind === "text" && message.isTyping
        ? { ...message, isTyping: false }
        : message
    ));

    setConversations((current) => {
      const existing = current.find((conversation) => conversation.id === conversationId);
      const updated: StoredConversation = {
        version: 1,
        id: conversationId,
        title: existing?.title ?? fallbackConversationTitle(firstUserMessage.content),
        titleStatus: existing?.titleStatus ?? "pending",
        createdAt: existing?.createdAt ?? now,
        updatedAt: options.touch === false ? existing?.updatedAt ?? now : now,
        mode: options.modeOverride ?? mode,
        sessionId: activeSessionIdRef.current,
        messages: stableMessages,
      };
      return persistConversations([
        updated,
        ...current.filter((conversation) => conversation.id !== conversationId),
      ], now);
    });
  };

  const requestConversationTitle = (conversationId: string, conversationMessages: ChatMessageData[]) => {
    if (titleRequestIdsRef.current.has(conversationId)) return;
    const firstUser = conversationMessages.find((message) => (
      message.role === "user" && message.kind === "text" && message.content.trim()
    ));
    const successfulAssistant = [...conversationMessages].reverse().find((message) => (
      message.role === "assistant" && message.kind === "text" && message.content.trim() && !message.isTyping
    ));
    if (!firstUser || firstUser.kind !== "text" || !successfulAssistant || successfulAssistant.kind !== "text") return;
    const titleMessages = [
      { role: firstUser.role, content: firstUser.content },
      { role: successfulAssistant.role, content: successfulAssistant.content },
    ];

    titleRequestIdsRef.current.add(conversationId);
    void Promise.resolve().then(() => generateConversationTitle(titleMessages)).then((title) => {
      setConversations((current) => persistConversations(current.map((conversation) => (
        conversation.id === conversationId
          ? { ...conversation, title, titleStatus: "generated" as const }
          : conversation
      ))));
    }).catch(() => {
      setConversations((current) => persistConversations(current.map((conversation) => (
        conversation.id === conversationId
          ? { ...conversation, titleStatus: "fallback" as const }
          : conversation
      ))));
    });
  };

  const stopPolling = () => {
    if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
    pollAbortRef.current?.abort();
    pollAbortRef.current = null;
  };

  const isCurrentJob = (jobId: string | null, requestToken: string) => {
    const active = activeImageJobRef.current;
    return active !== null
      && active.requestToken === requestToken
      && active.jobId === jobId;
  };

  const updateImageStatus = (
    messageId: string,
    patch: Partial<Omit<ImageStatusChatMessage, "id" | "role" | "kind" | "prompt">>,
  ) => {
    if (!mountedRef.current) return;
    setMessages((current) => current.map((message) => (
      message.id === messageId && message.kind === "image-status"
        ? { ...message, ...patch }
        : message
    )));
  };

  const failImageJob = (active: ActiveImageJob, error: string) => {
    stopPolling();
    if (!isCurrentJob(active.jobId, active.requestToken)) return;
    activeImageJobRef.current = null;
    digitalHuman.notifyError(`image-${active.requestToken}`, "illustration");
    setMessages((current) => current.map((message) => {
      if (message.id === active.sourceMessageId && message.kind === "image-result") {
        return { ...message, historical: false };
      }
      if (message.id !== active.messageId) return message;
      if (message.kind === "image-result") return { ...message, stage: "awaiting_human_feedback" };
      if (message.kind === "image-status") return {
        ...message,
        jobId: active.jobId,
        requestToken: active.requestToken,
        stage: "failed",
        error,
        traceEvents: finishLocalTrace(message.traceEvents, "图像生成失败", error),
      };
      return message;
    }));
  };

  const schedulePoll = (
    active: ActiveImageJob,
    delay: number,
    failureCount = 0,
  ) => {
    if (!isCurrentJob(active.jobId, active.requestToken) || active.jobId === null) return;
    const scheduledDelay = document.visibilityState === "hidden"
      ? Math.max(delay, BACKGROUND_POLL_DELAY)
      : delay;
    pollTimerRef.current = window.setTimeout(() => {
      pollTimerRef.current = null;
      void pollImageJob(active.jobId as string, active.requestToken, failureCount);
    }, scheduledDelay);
  };

  const applyImageJob = (job: ImageJob, requestToken: string) => {
    if (!isCurrentJob(job.jobId, requestToken)) return;
    const active = activeImageJobRef.current;
    if (!active) return;

    if (runningImageStages.includes(job.stage)) {
      setMessages((current) => current.map((message) => {
        if (message.id !== active.messageId) return message;
        if (message.kind === "image-result") return {
          ...message, stage: job.stage, requestToken,
          ...(job.imageUrl ? { imageUrl: job.imageUrl } : {}),
          ...(job.imageId ? { imageId: job.imageId } : {}),
          traceId: job.traceId || message.traceId,
          traceEvents: job.traceEvents ?? message.traceEvents ?? [],
        };
        if (message.kind === "image-status") return { ...message, jobId: job.jobId, requestToken, stage: job.stage, error: progressCopy[job.stage], traceId: job.traceId || message.traceId, traceEvents: job.traceEvents ?? message.traceEvents ?? [] };
        return message;
      }));
      schedulePoll(active, NORMAL_POLL_DELAY);
      return;
    }

    if ((job.stage === "completed" || job.stage === "awaiting_human_feedback") && job.imageUrl && job.imageId) {
      stopPolling();
      activeImageJobRef.current = null;
      setImageHistory(saveImageHistoryEntry({
        prompt: active.prompt,
        jobId: job.jobId,
        imageUrl: job.imageUrl,
        imageId: job.imageId,
        autoRevisionCount: job.autoRevisionCount,
        revisionOrigin: job.revisionOrigin,
        traceId: job.traceId || "",
        traceEvents: job.traceEvents ?? [],
      }));
      if ((job.traceEvents?.length ?? 0) > 0) {
        pendingImageResultsRef.current.set(active.messageId, {
          job,
          requestToken,
          prompt: active.prompt,
        });
        updateImageStatus(active.messageId, {
          jobId: job.jobId,
          requestToken,
          stage: job.stage,
          error: null,
          traceId: job.traceId,
          traceEvents: job.traceEvents ?? [],
          isRevealingTrace: true,
        });
        return;
      }
      settleDigitalHumanForImage(job);
      setMessages((current) => current.map((message) => (
        message.id === active.messageId
          ? {
              id: active.messageId,
              role: "assistant",
              kind: "image-result",
              prompt: active.prompt,
              jobId: job.jobId,
              requestToken,
              imageUrl: job.imageUrl as string,
              imageId: job.imageId as string,
              stage: job.stage,
              candidateImageUrl: job.candidateImageUrl,
              previousImageUrl: job.previousImageUrl,
              previousImageId: job.previousImageId,
              criticResult: job.criticResult,
              guardResult: job.guardResult,
              autoRevisionCount: job.autoRevisionCount,
              revisionOrigin: job.revisionOrigin,
              previousRevisionOrigin: job.previousRevisionOrigin,
              traceId: job.traceId || "",
              traceEvents: job.traceEvents ?? [],
            }
          : message
      )));
      return;
    }

    stopPolling();
    activeImageJobRef.current = null;

    const cancelled = job.stage === "cancelled";
    if (!cancelled) digitalHuman.notifyError(`image-${requestToken}`, "illustration");
    updateImageStatus(active.messageId, {
      jobId: active.jobId,
      requestToken: active.requestToken,
      stage: job.stage,
      error: job.error || (cancelled ? "已取消本次图片生成" : "图片生成失败，请重新输入主题"),
    });
  };

  const pollImageJob = async (jobId: string, requestToken: string, failureCount: number) => {
    if (!isCurrentJob(jobId, requestToken)) return;
    const controller = new AbortController();
    pollAbortRef.current = controller;

    try {
      const job = await getImageJob(jobId, controller.signal);
      if (!isCurrentJob(jobId, requestToken) || job.jobId !== jobId) return;
      applyImageJob(job, requestToken);
    } catch (error) {
      if (isAbortError(error) || !isCurrentJob(jobId, requestToken)) return;
      const active = activeImageJobRef.current;
      if (!active) return;

      if (error instanceof ImageJobRequestError && error.status === 404) {
        failImageJob(active, "未找到图片任务，请重新输入主题");
        return;
      }
      if (error instanceof ImageJobRequestError && error.status === 409) {
        updateImageStatus(active.messageId, { error: "任务状态正在同步" });
        schedulePoll(active, NORMAL_POLL_DELAY);
        return;
      }

      const isTransient = error instanceof TypeError
        || (error instanceof ImageJobRequestError && error.status >= 500);
      if (isTransient && failureCount < POLL_BACKOFF_DELAYS.length) {
        updateImageStatus(active.messageId, { error: "网络波动，正在重新连接…" });
        schedulePoll(active, POLL_BACKOFF_DELAYS[failureCount], failureCount + 1);
        return;
      }

      failImageJob(active, "图片生成失败，请重新输入主题");
    } finally {
      if (pollAbortRef.current === controller) pollAbortRef.current = null;
    }
  };

  const beginImageRequest = async (
    active: ActiveImageJob,
    request: (signal: AbortSignal) => Promise<ImageJob>,
  ) => {
    const controller = new AbortController();
    createAbortRef.current = controller;
    try {
      const job = await request(controller.signal);
      const current = activeImageJobRef.current;
      if (!mountedRef.current || current?.requestToken !== active.requestToken) {
        void cancelImageJob(job.jobId).catch(() => undefined);
        return;
      }
      current.jobId = job.jobId;
      applyImageJob(job, active.requestToken);
    } catch (error) {
      if (isAbortError(error) || activeImageJobRef.current?.requestToken !== active.requestToken) return;
      failImageJob(activeImageJobRef.current, "图片生成失败，请重新输入主题");
    } finally {
      if (createAbortRef.current === controller) createAbortRef.current = null;
    }
  };

  const startIllustration = (prompt: string) => {
    if (!prompt.trim() || activeImageJobRef.current) return;
    digitalHuman.markMeaningfulInteraction();
    const requestToken = `image-request-${Date.now()}-${++requestSequenceRef.current}`;
    const messageId = `image-status-${requestToken}`;

    const localDemo = findLocalIllustrationDemo(prompt);
    if (localDemo) {
      const job = createLocalIllustrationDemoJob(localDemo);
      const nextMessages: ChatMessageData[] = [
        ...messages,
        { id: `user-${requestToken}`, role: "user", kind: "text", content: prompt },
        {
          id: messageId,
          role: "assistant",
          kind: "image-status",
          prompt,
          jobId: job.jobId,
          requestToken,
          stage: job.stage,
          error: null,
          traceId: job.traceId,
          traceEvents: job.traceEvents,
          isRevealingTrace: true,
        },
      ];
      pendingImageResultsRef.current.set(messageId, { job, requestToken, prompt });
      setMessages(nextMessages);
      persistConversationMessages(nextMessages, { modeOverride: "illustration" });
      setInput("");
      return;
    }

    const active: ActiveImageJob = { jobId: null, requestToken, prompt, messageId };
    activeImageJobRef.current = active;
    const nextMessages: ChatMessageData[] = [
      ...messages,
      { id: `user-${requestToken}`, role: "user", kind: "text", content: prompt },
      {
        id: messageId,
        role: "assistant",
        kind: "image-status",
        prompt,
        jobId: null,
        requestToken,
        stage: "submitting",
        error: "正在创建图解任务…",
        traceEvents: [],
      },
    ];
    setMessages(nextMessages);
    persistConversationMessages(nextMessages, { modeOverride: "illustration" });
    setInput("");
    void beginImageRequest(active, (signal) => createImageJob(prompt, signal));
  };

  const revealPendingImageResult = (messageId: string) => {
    const pending = pendingImageResultsRef.current.get(messageId);
    if (!pending) return;
    pendingImageResultsRef.current.delete(messageId);
    const { job, requestToken, prompt } = pending;
    settleDigitalHumanForImage(job);
    setMessages((current) => current.map((message) => (
      message.id === messageId && message.kind === "image-status"
        ? {
            id: messageId,
            role: "assistant",
            kind: "image-result",
            prompt,
            jobId: job.jobId,
            requestToken,
            imageUrl: job.imageUrl as string,
            imageId: job.imageId as string,
            stage: job.stage,
            candidateImageUrl: job.candidateImageUrl,
            previousImageUrl: job.previousImageUrl,
            previousImageId: job.previousImageId,
            criticResult: job.criticResult,
            guardResult: job.guardResult,
            autoRevisionCount: job.autoRevisionCount,
            revisionOrigin: job.revisionOrigin,
            previousRevisionOrigin: job.previousRevisionOrigin,
            traceId: job.traceId,
            traceEvents: job.traceEvents,
          }
        : message
    )));
  };

  const submitImageEdit = (
    message: ImageResultChatMessage, bbox: NormalizedBBox, request: string,
  ) => {
    if (activeImageJobRef.current) return;
    digitalHuman.markMeaningfulInteraction();
    const requestToken = `image-edit-${Date.now()}-${++requestSequenceRef.current}`;
    const messageId = `image-status-${requestToken}`;
    const active: ActiveImageJob = {
      jobId: message.jobId,
      requestToken,
      prompt: message.prompt,
      messageId,
      sourceMessageId: message.id,
    };
    activeImageJobRef.current = active;
    setMessages((current) => [
      ...current.map((item) => item.id === message.id && item.kind === "image-result"
        ? { ...item, historical: true }
        : item),
      {
        id: `user-${requestToken}`,
        role: "user",
        kind: "text",
        content: `修改图片：${request}`,
      },
      {
        id: messageId,
        role: "assistant",
        kind: "image-status",
        prompt: message.prompt,
        jobId: message.jobId,
        requestToken,
        stage: "queued",
        error: null,
        traceEvents: [],
      },
    ]);
    void beginImageRequest(active, (signal) => editImageJob(message.jobId, message.imageId, bbox, request, signal));
  };

  const setAcceptImageError = (messageId: string, acceptError: string) => {
    if (!mountedRef.current) return;
    setMessages((current) => current.map((item) => item.id === messageId && item.kind === "image-result"
      ? { ...item, acceptError }
      : item));
  };

  const acceptImageResult = async (message: ImageResultChatMessage) => {
    if (activeImageJobRef.current) {
      setAcceptImageError(message.id, "有图解任务正在进行，请等待完成后再确认采用。");
      return;
    }
    try {
      await acceptImageJob(message.jobId);
      setMessages((current) => current.map((item) => item.id === message.id && item.kind === "image-result"
        ? {
            ...item,
            stage: "completed",
            accepted: true,
            acceptError: undefined,
            candidateImageUrl: undefined,
            previousImageUrl: undefined,
            previousImageId: undefined,
            criticResult: undefined,
            guardResult: undefined,
          }
        : item));
    } catch (error) {
      setAcceptImageError(
        message.id,
        error instanceof ImageJobRequestError && error.message
          ? error.message
          : "接受结果失败，请稍后重试。",
      );
      setMessages((current) => current.map((item) => item.id === message.id && item.kind === "image-result"
        ? { ...item, stage: "awaiting_human_feedback" } : item));
    }
  };

  const restorePreviousImageResult = async (message: ImageResultChatMessage) => {
    if (activeImageJobRef.current) return;
    try {
      const job = await restorePreviousImageJob(message.jobId, message.imageId);
      if (!job.imageUrl || !job.imageId) throw new Error("restored image is unavailable");
      setMessages((current) => current.map((item) => item.id === message.id && item.kind === "image-result"
        ? {
            ...item,
            imageUrl: job.imageUrl,
            imageId: job.imageId,
            stage: job.stage,
            candidateImageUrl: job.candidateImageUrl,
            previousImageUrl: job.previousImageUrl,
            previousImageId: job.previousImageId,
            criticResult: job.criticResult,
            guardResult: job.guardResult,
            revisionOrigin: job.revisionOrigin,
            previousRevisionOrigin: job.previousRevisionOrigin,
            traceId: job.traceId || item.traceId,
            traceEvents: job.traceEvents ?? item.traceEvents,
          }
        : item));
    } catch {
      // Preserve the current image if the rollback is stale or unavailable.
    }
  };

  const cancelIllustration = async (reason: CancelReason) => {
    const active = activeImageJobRef.current;
      if (!active) return;
      pendingImageResultsRef.current.delete(active.messageId);
    updateImageStatus(active.messageId, { stage: "cancelling", error: "正在取消…" });
    stopPolling();
    createAbortRef.current?.abort();
    createAbortRef.current = null;
    activeImageJobRef.current = null;
    pendingCancellationRef.current.set(active.messageId, active.requestToken);

    const cancellationIsCurrent = () => (
      mountedRef.current
      && pendingCancellationRef.current.get(active.messageId) === active.requestToken
    );

    const finishCancellation = (stage: "cancelled" | "failed", error: string) => {
      if (!cancellationIsCurrent()) return;
      pendingCancellationRef.current.delete(active.messageId);
      setMessages((current) => current.map((message) => {
        if (message.id === active.sourceMessageId && message.kind === "image-result") {
          return { ...message, historical: false };
        }
        if (message.id !== active.messageId) return message;
        if (message.kind === "image-result") return { ...message, stage: "awaiting_human_feedback" };
        if (message.kind === "image-status") return {
          ...message,
          jobId: active.jobId,
          requestToken: active.requestToken,
          stage,
          error,
          traceEvents: finishLocalTrace(
            message.traceEvents,
            stage === "cancelled" ? "生成已取消" : "取消请求未确认",
            error,
          ),
        };
        return message;
      }));
    };

    if (active.jobId === null) {
      if (reason !== "unmount") finishCancellation("cancelled", "已取消本次图片生成");
      return;
    }

    try {
      await cancelImageJob(active.jobId);
      if (reason === "unmount") return;
      finishCancellation("cancelled", "已取消本次图片生成");
    } catch {
      if (reason === "unmount") return;
      finishCancellation("failed", "取消请求未确认，请重新输入主题");
    }
  };

  const handleImageLoadError = (messageId: string) => {
    digitalHuman.notifyError(`image-load-${messageId}`, "illustration");
    setMessages((current) => current.map((message) => (
      message.id === messageId && message.kind === "image-result"
        ? { id: message.id, role: "assistant", kind: "image-status", prompt: message.prompt, jobId: message.jobId, requestToken: message.requestToken, stage: "failed", error: "图片加载失败，请重新输入主题", traceId: message.traceId, traceEvents: message.traceEvents }
        : message
    )));
  };

  const typeAssistantAnswer = (messageId: string, answer: string, sources: KnowledgeSource[] = []) => new Promise<void>((resolve) => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const frames = reduceMotion ? [answer] : createTypingFrames(answer);
    let frameIndex = 0;
    typingResolveRef.current = resolve;

    setIsTypingAnswer(true);
    setMessages((current) => [
      ...current,
      { id: messageId, role: "assistant", kind: "text", content: "", isTyping: true, sources },
    ]);

    typingTimer.current = window.setInterval(() => {
      const isLastFrame = frameIndex >= frames.length - 1;
      const nextContent = frames[frameIndex];
      setMessages((current) => current.map((message) => (
        message.id === messageId && message.kind === "text"
          ? { ...message, content: nextContent, isTyping: !isLastFrame }
          : message
      )));
      frameIndex += 1;

      if (isLastFrame) {
        if (typingTimer.current) window.clearInterval(typingTimer.current);
        typingTimer.current = null;
        typingResolveRef.current = null;
        setIsTypingAnswer(false);
        resolve();
      }
    }, reduceMotion ? 0 : 24);
  });

  const invalidateChatRequest = () => {
    chatRequestSequenceRef.current += 1;
    chatAbortRef.current?.abort();
    chatAbortRef.current = null;
    if (typingTimer.current !== null) window.clearInterval(typingTimer.current);
    typingTimer.current = null;
    typingResolveRef.current?.();
    typingResolveRef.current = null;
    setIsAnswering(false);
    setIsTypingAnswer(false);
    setChatProgress(null);
  };

  const submitQuestion = async (question: string) => {
    const cleanQuestion = question.trim();
    if (!cleanQuestion || isAnswering) return;
    digitalHuman.markMeaningfulInteraction();
    const requestToken = ++chatRequestSequenceRef.current;
    chatAbortRef.current?.abort();
    const requestAbort = new AbortController();
    chatAbortRef.current = requestAbort;
    const isCurrentRequest = () => (
      mountedRef.current && chatRequestSequenceRef.current === requestToken
    );
    const preset = knowledgeTopics.find((topic) => topic.question === cleanQuestion);
    const recentHistory = messages
      .filter((message) => message.kind === "text" && message.content.trim() && !message.isTyping)
      .slice(-8)
      .map((message) => ({ role: message.role, content: message.content }));
    const userMessage: ChatMessageData = {
      id: `user-${Date.now()}-${requestToken}`,
      role: "user",
      kind: "text",
      content: cleanQuestion,
    };
    const messagesAfterQuestion = [...messages, userMessage];
    setMessages(messagesAfterQuestion);
    persistConversationMessages(messagesAfterQuestion, { modeOverride: "chat" });
    setInput("");
    setIsAnswering(true);
    setChatProgress("正在分析并改写科学问题…");
    setSelectedQuestionId(preset?.id ?? "");

    try {
      const localDemoAnswer = getLocalChatDemoAnswer(cleanQuestion);
      const result = localDemoAnswer
        ? { answer: localDemoAnswer, sources: [] as KnowledgeSource[], sessionId: undefined }
        : preset
        ? await generateChatAnswer({ question: cleanQuestion, presetAnswer: preset.answer })
        : await generateChatAnswerStream({
          question: cleanQuestion,
          presetAnswer: undefined,
          sessionId: activeSessionIdRef.current,
          history: recentHistory,
          signal: requestAbort.signal,
        }, (message) => {
          if (isCurrentRequest()) setChatProgress(message);
        });
      if (!isCurrentRequest()) return;
      setChatProgress(null);
      if (!localDemoAnswer && !preset && result.sessionId) activeSessionIdRef.current = result.sessionId;
      const assistantMessageId = `assistant-${Date.now()}-${requestToken}`;
      await typeAssistantAnswer(assistantMessageId, result.answer, result.sources);
      if (isCurrentRequest()) {
        const completedMessages: ChatMessageData[] = [
          ...messagesAfterQuestion,
          { id: assistantMessageId, role: "assistant", kind: "text", content: result.answer, sources: result.sources },
        ];
        persistConversationMessages(completedMessages, { modeOverride: "chat" });
        const conversationId = activeConversationIdRef.current;
        if (conversationId) requestConversationTitle(conversationId, completedMessages);
        digitalHuman.notifySuccess(`chat-${requestToken}`);
      }
    } catch (error) {
      if (!isCurrentRequest()) return;
      digitalHuman.notifyError(`chat-${requestToken}`, "chat");
      if (error instanceof ChatRequestError && error.status === 409) {
        activeSessionIdRef.current = null;
        clearChatSessionId();
        const failedMessages: ChatMessageData[] = [
          ...messagesAfterQuestion,
          {
            id: `assistant-error-${Date.now()}`,
            role: "assistant",
            kind: "text",
            content: "本次会话已失效，请重新提问。",
          },
        ];
        setMessages(failedMessages);
        persistConversationMessages(failedMessages, { modeOverride: "chat" });
        return;
      }
      const errorContent = error instanceof ChatRequestError && error.detail
        ? error.detail
        : "回答生成过程中出现异常，请重新提问；若持续发生，请联系管理员查看后端日志。";
      const failedMessages: ChatMessageData[] = [
        ...messagesAfterQuestion,
        {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          kind: "text",
          content: errorContent,
        },
      ];
      setMessages(failedMessages);
      persistConversationMessages(failedMessages, { modeOverride: "chat" });
    } finally {
      if (!isCurrentRequest()) return;
      setIsAnswering(false);
      setChatProgress(null);
      if (chatAbortRef.current === requestAbort) chatAbortRef.current = null;
    }
  };

  const handleSubmit = (value: string) => {
    if (mode === "illustration") startIllustration(value);
    else void submitQuestion(value);
  };

  const chooseSuggestedQuestion = (topic: (typeof knowledgeTopics)[number]) => {
    if (!isAnswering) void submitQuestion(topic.question);
  };

  const handleModeChange = (nextMode: ChatMode) => {
    if (nextMode === mode) return;
    if (mode === "illustration" && activeImageJobRef.current) {
      void cancelIllustration("mode-switch");
    }
    if (mode === "illustration" && nextMode === "chat") {
      // A completed illustration belongs to the recent-conversations archive,
      // rather than becoming the starting state of the next Q&A session.
      persistConversationMessages(messages, { modeOverride: "illustration" });
      suppressConversationPersistenceRef.current = true;
      setMessages([]);
      setInput("");
      setSelectedQuestionId("");
      activeConversationIdRef.current = null;
      activeSessionIdRef.current = null;
      setActiveConversationId(null);
    }
    if (nextMode === "illustration") {
      invalidateChatRequest();
      setMessages([]);
      setSelectedQuestionId("");
      clearChatSessionId();
      activeConversationIdRef.current = null;
      activeSessionIdRef.current = null;
      setActiveConversationId(null);
    }
    setMode(nextMode);
  };

  const selectDigitalHumanTemplate = (template: DigitalHumanTemplate) => {
    digitalHuman.markMeaningfulInteraction();
    setInput(template.prompt);
    digitalHuman.closePromptPanel();
    window.requestAnimationFrame(() => chatInputRef.current?.focus());
  };

  const openConversation = (conversation: StoredConversation) => {
    invalidateChatRequest();
    if (activeImageJobRef.current) void cancelIllustration("mode-switch");
    suppressConversationPersistenceRef.current = true;
    activeConversationIdRef.current = conversation.id;
    activeSessionIdRef.current = conversation.sessionId;
    setActiveConversationId(conversation.id);
    setMode(conversation.mode);
    setMessages(conversation.messages);
    setSelectedQuestionId("");
    setInput("");
    clearChatSessionId();
  };

  const deleteConversation = (conversation: StoredConversation) => {
    setConversations((current) => persistConversations(
      current.filter((candidate) => candidate.id !== conversation.id),
    ));
    if (activeConversationIdRef.current !== conversation.id) return;

    invalidateChatRequest();
    if (activeImageJobRef.current) void cancelIllustration("conversation-delete");
    suppressConversationPersistenceRef.current = true;
    activeConversationIdRef.current = null;
    activeSessionIdRef.current = null;
    setActiveConversationId(null);
    setMessages([]);
    setSelectedQuestionId("");
    setInput("");
    clearChatSessionId();
  };

  useEffect(() => {
    mountedRef.current = true;
    clearChatSessionId();
    preloadVirusDiaryAssets();
    return () => {
      mountedRef.current = false;
      chatRequestSequenceRef.current += 1;
      if (typingTimer.current) window.clearInterval(typingTimer.current);
      typingResolveRef.current = null;
      void cancelIllustration("unmount");
    };
  }, []);

  useEffect(() => {
    const nextExpiry = Math.min(...imageHistory.map((entry) => entry.expiresAt));
    if (!Number.isFinite(nextExpiry)) return;
    const timer = window.setTimeout(
      () => setImageHistory(loadImageHistory()),
      Math.max(0, Math.min(nextExpiry - Date.now() + 50, 2_147_000_000)),
    );
    return () => window.clearTimeout(timer);
  }, [imageHistory]);

  useEffect(() => {
    if (typeof window.addEventListener !== "function") return;
    const syncHistory = (event: StorageEvent) => {
      if (event.key === IMAGE_HISTORY_STORAGE_KEY) setImageHistory(loadImageHistory());
    };
    window.addEventListener("storage", syncHistory);
    return () => window.removeEventListener("storage", syncHistory);
  }, []);

  useEffect(() => {
    if (suppressConversationPersistenceRef.current) {
      suppressConversationPersistenceRef.current = false;
      return;
    }
    if (messages.some((message) => message.kind === "text" && message.isTyping)) return;
    if (!activeConversationIdRef.current || !messages.some((message) => (
      message.role === "user" && message.kind === "text" && message.content.trim()
    ))) return;
    const timer = window.setTimeout(() => persistConversationMessages(messages), 220);
    return () => window.clearTimeout(timer);
  }, [messages]);

  return (
    <main className="app-shell">
      {activePage === "answer" && (
        <div className="app-frame app-frame--answer clinical-workspace">
          <WorkspaceNavigation
            conversations={conversations}
            activeConversationId={activeConversationId}
            onConversationSelect={openConversation}
            onConversationDelete={deleteConversation}
            onGraph={() => setActivePage("graph")}
            onInteractive={() => setActivePage("interactive")}
            onVideo={() => setActivePage("video")}
          />
          <section className="clinical-workspace__main" aria-label="疫苗知识 AI 对话工作区">
            <header className="clinical-workspace__header">
              <div>
                <h1>AI 疫苗知识助手</h1>
              </div>
            </header>
            <ChatPanel
              messages={messages}
              input={input}
              isAnswering={isAnswering}
              isTypingAnswer={isTypingAnswer}
              chatProgress={chatProgress}
              selectedQuestionId={selectedQuestionId}
              mode={mode}
              onInputChange={setInput}
              onSubmit={handleSubmit}
              onSelectQuestion={chooseSuggestedQuestion}
              onModeChange={handleModeChange}
              onCancelImage={() => void cancelIllustration("user")}
              onImageLoadError={handleImageLoadError}
              onAcceptImage={(message) => void acceptImageResult(message)}
              onRestorePreviousImage={(message) => void restorePreviousImageResult(message)}
              onEditImage={submitImageEdit}
              onImageTraceRevealComplete={revealPendingImageResult}
              inputRef={chatInputRef}
              onMeaningfulInteraction={digitalHuman.markMeaningfulInteraction}
            />
          </section>
          <AssistantContextPanel
            onHistory={() => {
              digitalHuman.markMeaningfulInteraction();
              setHistoryOpen(true);
            }}
            state={digitalHuman.state}
            bubble={digitalHuman.activeBubble}
            panelOpen={digitalHuman.isPromptPanelOpen}
            panelTitle={digitalHuman.panelTitle}
            templates={digitalHuman.templates}
            onAvatarActivate={digitalHuman.togglePromptPanel}
            onPanelClose={digitalHuman.closePromptPanel}
            onTemplateSelect={selectDigitalHumanTemplate}
          />
          <header className="clinical-mobile-header">
            <strong>疫苗智绘</strong>
            <div>
              <button data-testid="mobile-image-history-entry" type="button" onClick={() => { digitalHuman.markMeaningfulInteraction(); setHistoryOpen(true); }} aria-label="打开历史记录">历史</button>
              <AdminEntryLink />
            </div>
          </header>
          <nav className="clinical-mobile-nav" aria-label="移动端主要导航">
            <button className="is-active" type="button" aria-current="page">问答</button>
            <button type="button" onClick={() => setActivePage("graph")}>图谱</button>
            <button type="button" onClick={() => setActivePage("interactive")}>互动</button>
            <button type="button" onClick={() => setActivePage("video")}>视频</button>
          </nav>
          <ImageHistoryModal entries={imageHistory} open={historyOpen} onClose={() => setHistoryOpen(false)} />
        </div>
      )}

      {activePage === "graph" && (
        <Suspense fallback={<div className="graph-route-loading">正在打开知识图谱观测台…</div>}>
          <KnowledgeGraphViewer onClose={() => setActivePage("answer")} />
        </Suspense>
      )}

      <InteractiveExperiencePicker
        open={activePage === "interactive"}
        onClose={() => setActivePage("answer")}
        onDiary={() => setActivePage("virus-diary")}
        onSimulation={() => setActivePage("virus-spreading")}
      />

      {activePage === "virus-diary" && (
        <section
          className="full-page-experience full-page-experience--immune"
          data-testid="immune-page"
          aria-label="交互页面"
        >
          <InteractiveDemoModal open embedded onClose={() => setActivePage("answer")} />
        </section>
      )}

      {activePage === "virus-spreading" && (
        <section className="full-page-experience full-page-experience--spread" data-testid="virus-spreading-page" aria-label="病毒传播模拟页面">
          <VirusSpreadingSimulation onClose={() => setActivePage("answer")} />
        </section>
      )}

      {activePage === "video" && (
        <section className="full-page-experience" aria-label="科普短视频">
          <VideoGenerationModal
            open
            embedded
            onClose={() => setActivePage("answer")}
          />
        </section>
      )}
    </main>
  );
}
