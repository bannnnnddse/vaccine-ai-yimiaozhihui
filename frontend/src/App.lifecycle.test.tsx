import { StrictMode, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class TestNode {
  nodeType = 1;
  nodeName: string;
  tagName: string;
  namespaceURI = "http://www.w3.org/1999/xhtml";
  ownerDocument: TestDocument;
  parentNode: TestNode | null = null;
  childNodes: TestNode[] = [];
  attributes = new Map<string, string>();
  listeners = new Map<string, Set<(event: TestEvent) => void>>();
  style = { setProperty: () => undefined, removeProperty: () => undefined };

  constructor(tagName: string, ownerDocument: TestDocument) {
    this.tagName = tagName.toUpperCase();
    this.nodeName = this.tagName;
    this.ownerDocument = ownerDocument;
  }

  get firstChild() { return this.childNodes[0] ?? null; }
  get lastChild() { return this.childNodes.at(-1) ?? null; }
  get className() { return this.attributes.get("class") ?? ""; }
  set className(value: string) { this.attributes.set("class", value); }
  get textContent(): string { return this.childNodes.map((child) => child.textContent).join(""); }
  set textContent(value: string) {
    this.childNodes = value ? [this.ownerDocument.createTextNode(value)] : [];
  }
  appendChild(child: TestNode) { child.parentNode = this; this.childNodes.push(child); return child; }
  insertBefore(child: TestNode, before: TestNode | null) {
    child.parentNode = this;
    const index = before ? this.childNodes.indexOf(before) : -1;
    if (index < 0) this.childNodes.push(child);
    else this.childNodes.splice(index, 0, child);
    return child;
  }
  removeChild(child: TestNode) {
    this.childNodes = this.childNodes.filter((candidate) => candidate !== child);
    child.parentNode = null;
    return child;
  }
  setAttribute(name: string, value: unknown) { this.attributes.set(name, String(value)); }
  removeAttribute(name: string) { this.attributes.delete(name); }
  hasAttribute(name: string) { return this.attributes.has(name); }
  getAttribute(name: string) { return this.attributes.get(name) ?? null; }
  addEventListener(type: string, listener: (event: TestEvent) => void) {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }
  removeEventListener(type: string, listener: (event: TestEvent) => void) {
    this.listeners.get(type)?.delete(listener);
  }
  dispatchEvent(event: TestEvent) {
    event.target ??= this;
    event.currentTarget = this;
    for (const listener of this.listeners.get(event.type) ?? []) listener(event);
    this.parentNode?.dispatchEvent(event);
    return true;
  }
}

class TestTextNode extends TestNode {
  override nodeType = 3;
  data: string;
  constructor(value: string, ownerDocument: TestDocument) {
    super("#text", ownerDocument);
    this.data = value;
    this.nodeName = "#text";
  }
  get nodeValue() { return this.data; }
  set nodeValue(value: string) { this.data = value; }
  override get textContent() { return this.data; }
  override set textContent(value: string) { this.data = value; }
}

class TestDocument extends TestNode {
  override nodeType = 9;
  visibilityState: "visible" | "hidden" = "visible";
  documentElement: TestNode;
  body: TestNode;
  defaultView: Record<string, unknown> | null = null;
  activeElement: TestNode | null = null;
  constructor() {
    super("#document", null as unknown as TestDocument);
    this.ownerDocument = this;
    this.documentElement = new TestNode("html", this);
    this.body = new TestNode("body", this);
    this.documentElement.appendChild(this.body);
  }
  createElement(tagName: string) { return new TestNode(tagName, this); }
  createElementNS(_namespace: string, tagName: string) { return this.createElement(tagName); }
  createTextNode(value: string) { return new TestTextNode(value, this); }
}

interface TestEvent {
  type: string;
  target?: TestNode;
  currentTarget?: TestNode;
}

const service = vi.hoisted(() => {
  class RequestError extends Error {
    constructor(message: string, public readonly status: number, public readonly detail?: string) {
      super(message);
    }
  }
  return {
    RequestError,
    ChatRequestError: RequestError,
    createImageJob: vi.fn(),
    getImageJob: vi.fn(),
    cancelImageJob: vi.fn(),
    editImageJob: vi.fn(),
    acceptImageJob: vi.fn(),
    generateChatAnswer: vi.fn(),
    generateConversationTitle: vi.fn(),
  };
});

const chatSession = vi.hoisted(() => ({
  readChatSessionId: vi.fn(),
  writeChatSessionId: vi.fn(),
  clearChatSessionId: vi.fn(),
}));

vi.mock("./services/generationService", () => ({
  ImageJobRequestError: service.RequestError,
  ChatRequestError: service.ChatRequestError,
  createImageJob: service.createImageJob,
  getImageJob: service.getImageJob,
  cancelImageJob: service.cancelImageJob,
  editImageJob: service.editImageJob,
  acceptImageJob: service.acceptImageJob,
  generateChatAnswer: service.generateChatAnswer,
  generateChatAnswerStream: (request: { signal?: AbortSignal }) => {
    const { signal: _signal, ...requestWithoutSignal } = request;
    return service.generateChatAnswer(requestWithoutSignal);
  },
  generateConversationTitle: service.generateConversationTitle,
}));

vi.mock("./services/chatSession", () => chatSession);

vi.mock("./components/AvatarGuide", () => ({ AvatarGuide: () => null }));
vi.mock("./components/FeatureEntryCards", () => ({
  FeatureEntryCards: (props: { onInteractive: () => void }) => (
    <button data-testid="navigate-interactive" onClick={props.onInteractive}>互动体验</button>
  ),
}));
vi.mock("./components/InteractiveDemoModal", () => ({
  InteractiveDemoModal: (props: { embedded?: boolean }) => (
    <div data-testid="immune-modal" data-embedded={String(props.embedded)} />
  ),
}));
vi.mock("./components/virus-spreading/VirusSpreadingSimulation", () => ({
  VirusSpreadingSimulation: () => <div data-testid="virus-spreading-game">疫苗防线</div>,
}));
vi.mock("./components/VideoGenerationModal", () => ({
  VideoGenerationModal: (props: { embedded?: boolean; onClose: () => void }) => (
    <section data-testid="science-video-page" data-embedded={String(props.embedded)}>
      <button data-testid="close-science-video" onClick={props.onClose}>关闭</button>
    </section>
  ),
}));
vi.mock("./components/ChatPanel", () => ({
  ChatPanel: (props: {
    messages: unknown[];
    mode?: string;
    onModeChange?: (mode: "chat" | "illustration") => void;
    onSubmit: (prompt: string) => void;
    onCancelImage?: () => void;
    onImageLoadError?: (messageId: string) => void;
    onImageTraceRevealComplete?: (messageId: string) => void;
    onEditImage?: (
      message: Record<string, unknown>,
      bbox: [number, number, number, number],
      request: string,
    ) => void;
    onAcceptImage?: (message: Record<string, unknown>) => void;
  }) => (
    <section data-testid="chat" data-mode={props.mode} data-messages={JSON.stringify(props.messages)}>
      <button data-testid="custom-first" onClick={() => props.onSubmit("自定义问题一")}>自定义问题一</button>
      <button data-testid="custom-second" onClick={() => props.onSubmit("自定义问题二")}>自定义问题二</button>
      <button data-testid="follow-up" onClick={() => props.onSubmit("为什么？")}>为什么</button>
      <button data-testid="preset" onClick={() => props.onSubmit("疫苗是如何进入体内发挥作用的？")}>预设问题</button>
      <button data-testid="illustration" onClick={() => props.onModeChange?.("illustration")}>图解</button>
      <button data-testid="chat-mode" onClick={() => props.onModeChange?.("chat")}>问答</button>
      <button data-testid="submit" onClick={() => props.onSubmit("疫苗如何建立免疫记忆")}>提交</button>
      <button data-testid="flu-vaccine-demo" onClick={() => props.onSubmit("流感疫苗有什么作用，请给我图解")}>流感疫苗图解演示</button>
      <button data-testid="breakthrough-demo" onClick={() => props.onSubmit("打了疫苗为什么还会感染？那疫苗到底有没有用？")}>突破性感染演示</button>
      <button data-testid="cancel" onClick={() => props.onCancelImage?.()}>取消</button>
      {props.messages.flatMap((message) => {
        const imageMessage = message as { id?: string; kind?: string; historical?: boolean; isRevealingTrace?: boolean };
        if (imageMessage.kind === "image-status" && imageMessage.id && imageMessage.isRevealingTrace) {
          return <button key={`${imageMessage.id}-trace`} data-testid="finish-image-trace" onClick={() => props.onImageTraceRevealComplete?.(imageMessage.id!)}>完成过程文字</button>;
        }
        return imageMessage.kind === "image-result" && imageMessage.id
          ? [
              <button key={`${imageMessage.id}-error`} data-testid="image-error" onClick={() => props.onImageLoadError?.(imageMessage.id!)}>图片加载失败</button>,
              <button key={`${imageMessage.id}-accept`} data-testid="accept-image" onClick={() => props.onAcceptImage?.(message as Record<string, unknown>)}>接受结果</button>,
              ...(!imageMessage.historical ? [<button
                key={`${imageMessage.id}-edit`}
                data-testid="edit-image"
                onClick={() => props.onEditImage?.(
                  message as Record<string, unknown>,
                  [0.1, 0.05, 0.9, 0.25],
                  "删掉标题",
                )}
              >修改图片</button>] : []),
            ]
          : [];
      })}
    </section>
  ),
}));

import { App } from "./App";

function installDom(initialStorage: Record<string, string> = {}) {
  const document = new TestDocument();
  const storage = new Map(Object.entries(initialStorage));
  const window = {
    document,
    Node: TestNode,
    Element: TestNode,
    HTMLElement: TestNode,
    HTMLIFrameElement: class extends TestNode {},
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
    },
    matchMedia: () => ({ matches: true, addEventListener: () => undefined, removeEventListener: () => undefined }),
  };
  document.defaultView = window;
  Object.assign(globalThis, {
    IS_REACT_ACT_ENVIRONMENT: true,
    window,
    document,
    Node: TestNode,
    Element: TestNode,
    HTMLElement: TestNode,
    HTMLIFrameElement: window.HTMLIFrameElement,
  });
  return document;
}

function findByTestId(root: TestNode, id: string): TestNode {
  if (root.getAttribute("data-testid") === id) return root;
  for (const child of root.childNodes) {
    try { return findByTestId(child, id); } catch { /* keep searching */ }
  }
  throw new Error(`Missing test node: ${id}`);
}

function messages(container: TestNode) {
  return JSON.parse(findByTestId(container, "chat").getAttribute("data-messages") ?? "[]") as Array<Record<string, unknown>>;
}

async function click(container: TestNode, testId: string) {
  await act(async () => { findByTestId(container, testId).dispatchEvent({ type: "click" }); });
}

describe("App interactive route", () => {
  let root: Root;
  let container: TestNode;

  beforeEach(async () => {
    const document = installDom();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<App />));
  });

  afterEach(async () => {
    await act(async () => root.unmount());
  });

  it("offers two experiences and opens the virus diary fullscreen", async () => {
    await click(container, "navigate-interactive");
    expect(container.textContent).toContain("病毒日记");
    expect(container.textContent).toContain("疫苗防线");
    await click(container, "choose-virus-diary");

    expect(findByTestId(container, "immune-page").className).toContain("full-page-experience--immune");
    expect(findByTestId(container, "immune-modal").getAttribute("data-embedded")).toBe("true");
  });

  it("opens the local virus-spreading game instead of an external page", async () => {
    await click(container, "navigate-interactive");
    await click(container, "choose-virus-spreading");

    expect(findByTestId(container, "virus-spreading-page").textContent).toContain("疫苗防线");
  });

  it("opens and closes the local science-video collection without a generation lifecycle", async () => {
    await click(container, "navigate-video");
    expect(findByTestId(container, "science-video-page").getAttribute("data-embedded")).toBe("true");

    await click(container, "close-science-video");
    expect(findByTestId(container, "chat")).toBeTruthy();
  });

  it("shows the QA template invitation as soon as the answer page opens", () => {
    expect(findByTestId(container, "digital-human-bubble").textContent).toBe("不知道怎么问？点击我看看模板吧~");
  });

  it("shows the matching invitation every time the user switches modes", async () => {
    await click(container, "illustration");
    expect(findByTestId(container, "digital-human-bubble").textContent).toBe("想把疫苗知识变成图？描述你想了解的内容就可以。");

    await click(container, "chat-mode");
    expect(findByTestId(container, "digital-human-bubble").textContent).toBe("不知道怎么问？点击我看看模板吧~");
  });
});

describe("App image history bootstrap", () => {
  let root: Root;
  let container: TestNode;

  afterEach(async () => {
    await act(async () => root.unmount());
  });

  it("keeps a refreshed conversation empty while exposing saved images in the read-only archive", async () => {
    const now = Date.now();
    const storedEntry = {
      id: "image-history-job-refresh-v0",
      imageId: "job-refresh-v0",
      imageUrl: "/api/v1/generated-images/job-refresh-v0.png",
      jobId: "job-refresh",
      prompt: "刷新后仍在历史中的图片",
      autoRevisionCount: 0,
      revisionOrigin: "initial",
      traceId: "trace-refresh",
      traceEvents: [{ id: "trace-refresh-1", stage: "completed", title: "图解已准备完成", status: "completed", createdAt: new Date(now).toISOString() }],
      createdAt: now,
      expiresAt: now + 86_400_000,
    };
    const document = installDom({ "vaccine-ai.image-history.v2": JSON.stringify([storedEntry]) });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<App />));

    expect(messages(container)).toEqual([]);
    expect(findByTestId(container, "chat").getAttribute("data-mode")).toBe("chat");
    await click(container, "image-history-entry");
    expect(findByTestId(container, "image-history-modal").textContent).toContain("刷新后仍在历史中的图片");
    expect(findByTestId(container, "image-history-modal").textContent).not.toContain("修改这张图");
  });
});

describe("App recent conversation lifecycle", () => {
  let root: Root;
  let container: TestNode;

  afterEach(async () => {
    await act(async () => root.unmount());
    vi.useRealTimers();
  });

  it("starts empty after refresh, restores a complete conversation, and continues the same session", async () => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    service.generateConversationTitle.mockResolvedValue("不应重新生成");
    service.generateChatAnswer.mockResolvedValue({
      answer: "续聊回答",
      isVaccineRelated: true,
      sessionId: "response-restored-2",
      sources: [],
    });
    const updatedAt = Date.now() - 60_000;
    const stored = {
      version: 1,
      conversations: [{
        version: 1,
        id: "conversation-restored",
        title: "HPV疫苗接种程序",
        titleStatus: "generated",
        createdAt: updatedAt - 1_000,
        updatedAt,
        mode: "chat",
        sessionId: "response-restored-1",
        messages: [
          { id: "stored-user", role: "user", kind: "text", content: "HPV疫苗怎么接种？" },
          { id: "stored-assistant", role: "assistant", kind: "text", content: "按适用程序接种。", sources: [{ fileName: "指南.pdf", page: 5, content: "接种程序片段" }] },
        ],
      }],
    };
    const document = installDom({ "vaccine-ai.conversations.v1": JSON.stringify(stored) });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<App />));

    expect(messages(container)).toEqual([]);
    expect(findByTestId(container, "recent-conversation-list").textContent).toContain("HPV疫苗接种程序");

    await click(container, "recent-conversation-conversation-restored");
    expect(messages(container)).toEqual(stored.conversations[0].messages);

    await click(container, "follow-up");
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(service.generateChatAnswer).toHaveBeenCalledWith(expect.objectContaining({
      question: "为什么？",
      sessionId: "response-restored-1",
    }));
    expect(service.generateConversationTitle).not.toHaveBeenCalled();

    const raw = (globalThis.window as unknown as { localStorage: Storage }).localStorage
      .getItem("vaccine-ai.conversations.v1");
    const persisted = JSON.parse(raw ?? "{}") as { conversations: Array<Record<string, unknown>> };
    expect(persisted.conversations[0]).toEqual(expect.objectContaining({
      id: "conversation-restored",
      sessionId: "response-restored-2",
    }));
    expect(persisted.conversations[0].updatedAt).toEqual(expect.any(Number));
    expect(persisted.conversations[0].messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ content: "续聊回答" }),
    ]));
  });

  it("keeps the fallback title when background title generation fails", async () => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    service.generateChatAnswer.mockResolvedValue({
      answer: "正常回答",
      isVaccineRelated: true,
      sessionId: "response-title-failure",
      sources: [],
    });
    service.generateConversationTitle.mockRejectedValue(new Error("title unavailable"));
    const document = installDom();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<App />));

    await click(container, "custom-first");
    await act(async () => { await vi.runAllTimersAsync(); });

    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ content: "正常回答" }),
    ]));
    expect(findByTestId(container, "recent-conversation-list").textContent).toContain("自定义问题一");
    const raw = (globalThis.window as unknown as { localStorage: Storage }).localStorage
      .getItem("vaccine-ai.conversations.v1");
    const persisted = JSON.parse(raw ?? "{}") as { conversations: Array<Record<string, unknown>> };
    expect(persisted.conversations[0]).toEqual(expect.objectContaining({
      title: "自定义问题一",
      titleStatus: "fallback",
    }));
  });

  it("deletes a recent conversation from the list and local storage", async () => {
    const updatedAt = Date.now() - 60_000;
    const stored = {
      version: 1,
      conversations: [{
        version: 1,
        id: "conversation-delete",
        title: "待删除对话",
        titleStatus: "generated",
        createdAt: updatedAt - 1_000,
        updatedAt,
        mode: "chat",
        sessionId: "response-delete",
        messages: [
          { id: "delete-user", role: "user", kind: "text", content: "测试删除" },
          { id: "delete-assistant", role: "assistant", kind: "text", content: "测试回复" },
        ],
      }],
    };
    const document = installDom({ "vaccine-ai.conversations.v1": JSON.stringify(stored) });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<App />));

    await click(container, "delete-conversation-conversation-delete");

    expect(findByTestId(container, "recent-conversation-list").textContent).toContain("暂无最近对话");
    const raw = (globalThis.window as unknown as { localStorage: Storage }).localStorage
      .getItem("vaccine-ai.conversations.v1");
    expect(JSON.parse(raw ?? "{}").conversations).toEqual([]);
  });
});

describe("App illustration-job lifecycle", () => {
  let root: Root;
  let container: TestNode;

  beforeEach(async () => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    const document = installDom();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<App />));
    await click(container, "illustration");
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    vi.useRealTimers();
  });

  it("creates, recursively polls, and replaces the status with the completed image", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-1", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob
      .mockResolvedValueOnce({ jobId: "job-1", stage: "generating", autoRevisionCount: 0 })
      .mockResolvedValueOnce({ jobId: "job-1", stage: "completed", imageUrl: "/api/v1/generated-images/job-1-v0.png", imageId: "job-1-v0", autoRevisionCount: 0 });

    await click(container, "submit");
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ role: "user", kind: "text", content: "疫苗如何建立免疫记忆" }),
      expect.objectContaining({ kind: "image-status", stage: "queued", error: "任务排队中…" }),
    ]));

    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ stage: "generating", error: "正在生成科学图解…" }),
    ]));
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-result", imageUrl: "/api/v1/generated-images/job-1-v0.png" }),
    ]));
    expect(service.getImageJob).toHaveBeenCalledTimes(2);
  });

  it("waits for the final trace reveal before showing the completed image UI", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-trace", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob.mockResolvedValueOnce({
      jobId: "job-trace",
      stage: "completed",
      imageUrl: "/api/v1/generated-images/job-trace-v0.png",
      imageId: "job-trace-v0",
      autoRevisionCount: 0,
      traceId: "trace-final",
      traceEvents: [
        { id: "trace-final-1", stage: "visual_critic", title: "最终视觉审查完成", detail: "没有发现需要继续修正的明显问题。", status: "completed", createdAt: "2026-08-13T10:00:00Z" },
        { id: "trace-final-2", stage: "completed", title: "图解已准备完成", detail: "最终图片已生成。", status: "completed", createdAt: "2026-08-13T10:00:01Z" },
      ],
    });

    await click(container, "submit");
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });

    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-status", stage: "completed", isRevealingTrace: true }),
    ]));
    expect(messages(container).some((message) => message.kind === "image-result")).toBe(false);

    await click(container, "finish-image-trace");

    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-result", imageUrl: "/api/v1/generated-images/job-trace-v0.png" }),
    ]));
  });

  it("uses the local flu-vaccine illustration demo after its simulated trace", async () => {
    await click(container, "flu-vaccine-demo");

    expect(service.createImageJob).not.toHaveBeenCalled();
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "image-status",
        stage: "awaiting_human_feedback",
        isRevealingTrace: true,
        traceEvents: expect.arrayContaining([
          expect.objectContaining({ title: "正在理解图解需求" }),
          expect.objectContaining({ title: "正在组织科学表达" }),
        ]),
      }),
    ]));

    await click(container, "finish-image-trace");

    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "image-result",
        imageUrl: "/demo-flu-vaccine.png",
        imageId: "local-demo-flu-vaccine-v0",
        stage: "awaiting_human_feedback",
      }),
    ]));
  });

  it("archives an illustration and starts a blank Q&A session when returning to chat", async () => {
    await click(container, "flu-vaccine-demo");

    await click(container, "chat-mode");

    expect(findByTestId(container, "chat").getAttribute("data-mode")).toBe("chat");
    expect(messages(container)).toEqual([]);
    expect(findByTestId(container, "recent-conversation-list").textContent).toContain("流感疫苗有什么作用，请给我图解");
  });

  it("uses the local breakthrough-infection answer demo without calling the chat service", async () => {
    await click(container, "chat-mode");
    await click(container, "breakthrough-demo");
    await act(async () => { await vi.runOnlyPendingTimersAsync(); });

    expect(service.generateChatAnswer).not.toHaveBeenCalled();
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({
        role: "assistant",
        kind: "text",
        content: "疫苗不是一堵保证病毒永远进不来的墙，更像是提前交给身体的一张“通缉令”，也是一次安全的免疫演习。接种后，免疫系统会认识病毒身上的特征，产生抗体，并留下具有记忆能力的免疫细胞。等真正的病毒来临时，身体就不必从头摸索，而能更快识别它、调动防线，在病毒造成更大伤害之前展开反击。\n\n当然，疫苗并不能保证每个人、每一次都不被感染，因为免疫反应会随时间变化，病毒也可能发生变异。但“仍有可能感染”并不等于“疫苗没有作用”。它更重要的价值，是降低感染后的严重程度，减少重症和死亡的风险。我们接种疫苗，不只是为自己多穿一层防护衣，也是在为老人、孩子和免疫力较弱的人，多撑起一把伞。",
      }),
    ]));
  });

  it("uses the local breakthrough-infection illustration demo after its simulated trace", async () => {
    await click(container, "illustration");
    await click(container, "breakthrough-demo");

    expect(service.createImageJob).not.toHaveBeenCalled();
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "image-status",
        jobId: "local-demo-vaccine-breakthrough-infection",
        stage: "awaiting_human_feedback",
        isRevealingTrace: true,
      }),
    ]));

    await click(container, "finish-image-trace");

    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "image-result",
        imageUrl: "/demo-vaccine-breakthrough-infection.png",
        imageId: "local-demo-vaccine-breakthrough-infection-v0",
        stage: "awaiting_human_feedback",
      }),
    ]));
  });

  it("keeps the previous image and appends the edit request, animation, and new image", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-history", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob
      .mockResolvedValueOnce({
        jobId: "job-history",
        stage: "completed",
        imageUrl: "/api/v1/generated-images/job-history-v0.png",
        imageId: "job-history-v0",
        autoRevisionCount: 0,
      })
      .mockResolvedValueOnce({
        jobId: "job-history",
        stage: "editing_with_bbox",
        imageUrl: "/api/v1/generated-images/job-history-v0.png",
        imageId: "job-history-v0",
        autoRevisionCount: 0,
      })
      .mockResolvedValueOnce({
        jobId: "job-history",
        stage: "completed",
        imageUrl: "/api/v1/generated-images/job-history-v1.png",
        imageId: "job-history-v1",
        autoRevisionCount: 0,
        revisionOrigin: "human",
      });
    service.editImageJob.mockResolvedValue({
      jobId: "job-history",
      stage: "queued",
      autoRevisionCount: 0,
    });

    await click(container, "submit");
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    await click(container, "edit-image");

    expect(service.editImageJob).toHaveBeenCalledWith(
      "job-history",
      "job-history-v0",
      [0.1, 0.05, 0.9, 0.25],
      "删掉标题",
      expect.anything(),
    );
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-result", imageId: "job-history-v0", historical: true }),
      expect.objectContaining({ role: "user", kind: "text", content: "修改图片：删掉标题" }),
      expect.objectContaining({ kind: "image-status", stage: "queued" }),
    ]));

    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-result", imageId: "job-history-v0", historical: true }),
      expect.objectContaining({ kind: "image-status", stage: "editing_with_bbox" }),
    ]));
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-result", imageUrl: "/api/v1/generated-images/job-history-v0.png", historical: true }),
      expect.objectContaining({ kind: "image-result", imageUrl: "/api/v1/generated-images/job-history-v1.png", revisionOrigin: "human" }),
    ]));
  });

  it("continues the image-job lifecycle after the StrictMode setup-cleanup-setup probe", async () => {
    await act(async () => root.unmount());
    const document = globalThis.document as unknown as TestDocument;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<StrictMode><App /></StrictMode>));
    await click(container, "illustration");

    service.createImageJob.mockResolvedValue({ jobId: "job-strict", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob.mockResolvedValue({ jobId: "job-strict", stage: "generating", autoRevisionCount: 0 });
    service.cancelImageJob.mockResolvedValue(undefined);

    await click(container, "submit");
    expect(service.cancelImageJob).not.toHaveBeenCalled();
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-status", stage: "queued" }),
    ]));
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(service.getImageJob).toHaveBeenCalledOnce();
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-status", stage: "generating" }),
    ]));
  });

  it("marks the image accepted after a successful accept call and clears review data", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-accept", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob.mockResolvedValueOnce({
      jobId: "job-accept",
      stage: "completed",
      imageUrl: "/api/v1/generated-images/job-accept-v0.png",
      imageId: "job-accept-v0",
      autoRevisionCount: 0,
      criticResult: { overallStatus: "pass", summary: "没有发现问题", recommendedAction: "accept", autoFixable: false, humanInputRequired: false, issues: [] },
    });
    service.acceptImageJob.mockResolvedValue(undefined);

    await click(container, "submit");
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    await click(container, "accept-image");

    expect(service.acceptImageJob).toHaveBeenCalledWith("job-accept");
    const accepted = messages(container).find((message) => message.kind === "image-result");
    expect(accepted).toMatchObject({ kind: "image-result", stage: "completed", accepted: true });
    expect(accepted).not.toHaveProperty("acceptError");
    expect(accepted).not.toHaveProperty("criticResult");
    expect(accepted).not.toHaveProperty("guardResult");
    expect(accepted).not.toHaveProperty("previousImageUrl");
  });

  it("surfaces an accept failure on the card instead of failing silently", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-accept-fail", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob.mockResolvedValueOnce({
      jobId: "job-accept-fail",
      stage: "completed",
      imageUrl: "/api/v1/generated-images/job-accept-fail-v0.png",
      imageId: "job-accept-fail-v0",
      autoRevisionCount: 0,
    });
    service.acceptImageJob.mockRejectedValue(new service.RequestError("任务未找到。", 404));

    await click(container, "submit");
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    await click(container, "accept-image");

    expect(service.acceptImageJob).toHaveBeenCalledWith("job-accept-fail");
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "image-result",
        stage: "awaiting_human_feedback",
        acceptError: "任务未找到。",
      }),
    ]));
  });

  it("treats 409 as synchronizing, then turns 404 into a terminal failure", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-2", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob
      .mockRejectedValueOnce(new service.RequestError("conflict", 409))
      .mockRejectedValueOnce(new service.RequestError("missing", 404));

    await click(container, "submit");
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ stage: "queued", error: "任务状态正在同步" }),
    ]));
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ stage: "failed", error: "未找到图片任务，请重新输入主题" }),
    ]));
  });

  it("stops polling before DELETE and releases the image input after cancellation", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-3", stage: "queued", autoRevisionCount: 0 });
    service.cancelImageJob.mockResolvedValue(undefined);

    await click(container, "submit");
    await click(container, "cancel");
    expect(service.cancelImageJob).toHaveBeenCalledWith("job-3");
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ stage: "cancelled", error: "已取消本次图片生成" }),
    ]));
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(service.getImageJob).not.toHaveBeenCalled();
  });

  it("uses 1500/3000/5000 backoff delays and fails after three retry attempts", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-backoff", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob.mockRejectedValue(new TypeError("network down"));

    await click(container, "submit");
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(service.getImageJob).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1_499); });
    expect(service.getImageJob).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(service.getImageJob).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    expect(service.getImageJob).toHaveBeenCalledTimes(3);
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(service.getImageJob).toHaveBeenCalledTimes(4);
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ stage: "failed", error: "图片生成失败，请重新输入主题" }),
    ]));
  });

  it("enforces a five-second minimum poll interval while the page is hidden", async () => {
    (globalThis.document as unknown as TestDocument).visibilityState = "hidden";
    service.createImageJob.mockResolvedValue({ jobId: "job-hidden", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob.mockResolvedValue({ jobId: "job-hidden", stage: "queued", autoRevisionCount: 0 });

    await click(container, "submit");
    await act(async () => { await vi.advanceTimersByTimeAsync(4_999); });
    expect(service.getImageJob).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(service.getImageJob).toHaveBeenCalledOnce();
  });

  it("ignores a completed GET response after cancellation", async () => {
    let resolvePoll!: (job: { jobId: string; stage: "completed"; imageUrl: string; imageId: string; autoRevisionCount: number }) => void;
    service.createImageJob.mockResolvedValue({ jobId: "job-stale", stage: "queued", autoRevisionCount: 0 });
    service.getImageJob.mockImplementation(() => new Promise((resolve) => { resolvePoll = resolve; }));
    service.cancelImageJob.mockResolvedValue(undefined);

    await click(container, "submit");
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    await click(container, "cancel");
    await act(async () => resolvePoll({
      jobId: "job-stale",
      stage: "completed",
      imageUrl: "/api/v1/generated-images/stale.png", imageId: "job-stale-v0", autoRevisionCount: 0,
    }));
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ stage: "cancelled", error: "已取消本次图片生成" }),
    ]));
    expect(messages(container).some((message) => message.kind === "image-result")).toBe(false);

  });

  it("turns a completed image with a load error into a compact failed message", async () => {
    service.createImageJob.mockResolvedValue({ jobId: "job-image-error", stage: "completed", imageUrl: "/api/v1/generated-images/broken.png", imageId: "job-image-error-v0", autoRevisionCount: 0 });

    await click(container, "submit");
    await click(container, "image-error");

    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "image-status", stage: "failed", error: "图片加载失败，请重新输入主题" }),
    ]));
  });
});

describe("App chat session lifecycle", () => {
  let root: Root;
  let container: TestNode;

  const settleAnswer = async () => {
    await act(async () => { await vi.runAllTimersAsync(); });
  };

  beforeEach(async () => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    chatSession.readChatSessionId.mockReturnValue(null);
    service.generateChatAnswer.mockResolvedValue({
      answer: "回答",
      isVaccineRelated: true,
      sessionId: "new-session-id",
      sources: [],
    });
    service.generateConversationTitle.mockResolvedValue("自动标题");
    const document = installDom();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<App />));
    chatSession.clearChatSessionId.mockClear();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    vi.useRealTimers();
  });

  it("keeps the returned session ID in the active in-memory conversation", async () => {
    await click(container, "custom-first");
    await settleAnswer();

    expect(service.generateChatAnswer).toHaveBeenCalledWith({
      question: "自定义问题一",
      presetAnswer: undefined,
      sessionId: null,
      history: [],
    });
    expect(chatSession.writeChatSessionId).not.toHaveBeenCalled();
  });

  it("forwards the saved session ID with the next custom question", async () => {
    chatSession.readChatSessionId
      .mockReturnValueOnce(null)
      .mockReturnValueOnce("saved-session-id");
    service.generateChatAnswer
      .mockResolvedValueOnce({ answer: "第一条回答", isVaccineRelated: true, sessionId: "saved-session-id", sources: [] })
      .mockResolvedValueOnce({ answer: "第二条回答", isVaccineRelated: true, sessionId: "updated-session-id", sources: [] });

    await click(container, "custom-first");
    await settleAnswer();
    await click(container, "custom-second");
    await settleAnswer();

    expect(service.generateChatAnswer).toHaveBeenNthCalledWith(2, {
      question: "自定义问题二",
      presetAnswer: undefined,
      sessionId: "saved-session-id",
      history: [
        { role: "user", content: "自定义问题一" },
        { role: "assistant", content: "第一条回答" },
      ],
    });
  });

  it("forwards visible custom and preset turns when resolving a later follow-up", async () => {
    chatSession.readChatSessionId.mockReturnValue("saved-session-id");
    service.generateChatAnswer
      .mockResolvedValueOnce({ answer: "自定义回答", isVaccineRelated: true, sessionId: "saved-session-id", sources: [] })
      .mockResolvedValueOnce({ answer: "预设回答", isVaccineRelated: true, sessionId: null, sources: [] })
      .mockResolvedValueOnce({ answer: "追问回答", isVaccineRelated: true, sessionId: "updated-session-id", sources: [] });

    await click(container, "custom-first");
    await settleAnswer();
    await vi.advanceTimersByTimeAsync(1);
    await click(container, "preset");
    await settleAnswer();
    await vi.advanceTimersByTimeAsync(1);
    await click(container, "follow-up");
    await settleAnswer();

    expect(service.generateChatAnswer).toHaveBeenNthCalledWith(3, {
      question: "为什么？",
      presetAnswer: undefined,
      sessionId: "saved-session-id",
      history: [
        { role: "user", content: "自定义问题一" },
        { role: "assistant", content: "自定义回答" },
        { role: "user", content: "疫苗是如何进入体内发挥作用的？" },
        { role: "assistant", content: "预设回答" },
      ],
    });
  });

  it("keeps local presets isolated from the saved model session", async () => {
    chatSession.readChatSessionId.mockReturnValue("saved-session-id");
    service.generateChatAnswer.mockResolvedValue({
      answer: "本地预设回答",
      isVaccineRelated: true,
      sessionId: null,
      sources: [],
    });

    await click(container, "preset");
    await settleAnswer();

    expect(service.generateChatAnswer).toHaveBeenCalledWith({
      question: "疫苗是如何进入体内发挥作用的？",
      presetAnswer: expect.any(String),
    });
    expect(chatSession.readChatSessionId).not.toHaveBeenCalled();
    expect(chatSession.writeChatSessionId).not.toHaveBeenCalled();
    expect(chatSession.clearChatSessionId).not.toHaveBeenCalled();
  });

  it("clears an expired session and shows the session-expired message for HTTP 409", async () => {
    service.generateChatAnswer.mockRejectedValue(new service.ChatRequestError("expired", 409));

    await click(container, "custom-first");
    await act(async () => undefined);

    expect(chatSession.clearChatSessionId).toHaveBeenCalledOnce();
    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ content: "本次会话已失效，请重新提问。" }),
    ]));
  });

  it("shows the backend detail message for non-session errors", async () => {
    service.generateChatAnswer.mockRejectedValue(
      new service.ChatRequestError("timeout", 504, "网络超时，请稍后重试。"),
    );

    await click(container, "custom-first");
    await act(async () => undefined);

    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({ content: "网络超时，请稍后重试。" }),
    ]));
  });

  it("clears the model session when entering illustration mode without recreating it on return", async () => {
    await click(container, "custom-first");
    await settleAnswer();
    chatSession.writeChatSessionId.mockClear();
    chatSession.clearChatSessionId.mockClear();

    await click(container, "illustration");
    await click(container, "chat-mode");

    expect(chatSession.clearChatSessionId).toHaveBeenCalledOnce();
    expect(chatSession.writeChatSessionId).not.toHaveBeenCalled();
  });

  it("saves the knowledge sources on the matching assistant message", async () => {
    service.generateChatAnswer.mockResolvedValue({
      answer: "带来源的回答",
      isVaccineRelated: true,
      sessionId: "new-session-id",
      sources: [
        { fileName: "指南.pdf", page: 12, content: "相关片段" },
      ],
    });

    await click(container, "custom-first");
    await settleAnswer();

    expect(messages(container)).toEqual(expect.arrayContaining([
      expect.objectContaining({
        role: "assistant",
        kind: "text",
        content: "带来源的回答",
        isTyping: false,
        sources: [{ fileName: "指南.pdf", page: 12, content: "相关片段" }],
      }),
    ]));
  });

  it("ignores a late custom answer after switching to illustration mode and back", async () => {
    let resolveAnswer!: (result: { answer: string; isVaccineRelated: boolean; sessionId: string; sources: { fileName: string; page: number; content: string }[] }) => void;
    let savedSessionId: string | null = "previous-session-id";
    chatSession.writeChatSessionId.mockImplementation((sessionId: string) => { savedSessionId = sessionId; });
    chatSession.clearChatSessionId.mockImplementation(() => { savedSessionId = null; });
    service.generateChatAnswer.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAnswer = resolve;
    }));

    await click(container, "custom-first");
    await click(container, "illustration");
    await click(container, "chat-mode");
    await act(async () => { resolveAnswer({ answer: "迟到的回答", isVaccineRelated: true, sessionId: "late-session-id", sources: [{ fileName: "迟到.pdf", page: 1, content: "迟到片段" }] }); });

    expect(savedSessionId).toBeNull();
    expect(chatSession.writeChatSessionId).not.toHaveBeenCalled();
    expect(messages(container)).toEqual([]);
  });
});
