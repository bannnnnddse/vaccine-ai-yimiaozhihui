import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CaptureSceneProps } from "./CaptureScene";

type Listener = (event: { type: string }) => void;

class TestNode {
  nodeType = 1;
  nodeName: string;
  tagName: string;
  namespaceURI = "http://www.w3.org/1999/xhtml";
  ownerDocument: TestDocument;
  parentNode: TestNode | null = null;
  childNodes: TestNode[] = [];
  attributes = new Map<string, string>();
  listeners = new Map<string, Set<Listener>>();
  style = {
    values: new Map<string, string>(),
    setProperty: (name: string, value: string) => this.style.values.set(name, value),
    removeProperty: (name: string) => this.style.values.delete(name),
  };

  constructor(tagName: string, ownerDocument: TestDocument) {
    this.tagName = tagName.toUpperCase();
    this.nodeName = this.tagName;
    this.ownerDocument = ownerDocument;
  }

  get firstChild() { return this.childNodes[0] ?? null; }
  get lastChild(): TestNode | null { return this.childNodes.at(-1) ?? null; }
  get className() { return this.attributes.get("class") ?? ""; }
  set className(value: string) { this.attributes.set("class", value); }
  get complete() { return metrics.imagesReady; }
  get naturalWidth() { return metrics.imagesReady ? 1024 : 0; }
  get offsetWidth() {
    if (this.className.includes("immune-capture-virus")) return metrics.virusWidth;
    if (this.className.includes("immune-capture-dendritic")) return metrics.targetWidth;
    return 0;
  }
  get offsetHeight() {
    if (this.className.includes("immune-capture-virus")) return metrics.virusHeight;
    if (this.className.includes("immune-capture-dendritic")) return metrics.targetHeight;
    return 0;
  }
  get clientWidth() {
    return this.className.includes("immune-capture-stage") ? metrics.stageWidth : 0;
  }
  get clientHeight() {
    return this.className.includes("immune-capture-stage") ? metrics.stageHeight : 0;
  }
  get textContent(): string { return this.childNodes.map((child) => child.textContent).join(""); }
  set textContent(value: string) {
    this.childNodes = value ? [this.ownerDocument.createTextNode(value)] : [];
  }

  appendChild(child: TestNode) {
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  insertBefore(child: TestNode, before: TestNode | null) {
    child.parentNode = this;
    const index = before ? this.childNodes.indexOf(before) : -1;
    if (index < 0) this.childNodes.push(child);
    else this.childNodes.splice(index, 0, child);
    return child;
  }
  removeChild(child: TestNode) {
    const index = this.childNodes.indexOf(child);
    if (index >= 0) this.childNodes.splice(index, 1);
    child.parentNode = null;
    return child;
  }
  setAttribute(name: string, value: unknown) { this.attributes.set(name, String(value)); }
  removeAttribute(name: string) { this.attributes.delete(name); }
  hasAttribute(name: string) { return this.attributes.has(name); }
  getAttribute(name: string) { return this.attributes.get(name) ?? null; }
  addEventListener(type: string, listener: Listener) {
    const listeners = this.listeners.get(type) ?? new Set<Listener>();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }
  removeEventListener(type: string, listener: Listener) { this.listeners.get(type)?.delete(listener); }
  dispatchEvent(event: { type: string; target?: TestNode; currentTarget?: TestNode }) {
    event.target ??= this;
    event.currentTarget = this;
    for (const listener of this.listeners.get(event.type) ?? []) listener(event);
    this.parentNode?.dispatchEvent(event);
    return true;
  }
}

class TestTextNode extends TestNode {
  nodeType = 3;
  data: string;
  constructor(value: string, ownerDocument: TestDocument) {
    super("#text", ownerDocument);
    this.data = value;
    this.nodeName = "#text";
  }
  override get textContent() { return this.data; }
  override set textContent(value: string) { this.data = value; }
}

class TestDocument extends TestNode {
  override nodeType = 9;
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

const metrics = {
  imagesReady: false,
  stageWidth: 0,
  stageHeight: 0,
  virusWidth: 0,
  virusHeight: 0,
  targetWidth: 0,
  targetHeight: 0,
  reducedMotion: false,
};

let resizeCallbacks: Array<() => void> = [];

function findByClass(root: TestNode, className: string): TestNode | null {
  if (root.className.split(" ").includes(className)) return root;
  for (const child of root.childNodes) {
    const match = findByClass(child, className);
    if (match) return match;
  }
  return null;
}

function installDom() {
  const document = new TestDocument();
  class TestResizeObserver {
    callback: () => void;
    disconnected = false;
    constructor(callback: () => void) {
      this.callback = () => { if (!this.disconnected) callback(); };
      resizeCallbacks.push(this.callback);
    }
    observe() {}
    disconnect() { this.disconnected = true; }
  }
  const window = {
    document,
    Node: TestNode,
    Element: TestNode,
    HTMLElement: TestNode,
    HTMLIFrameElement: class extends TestNode {},
    ResizeObserver: TestResizeObserver,
    setTimeout,
    clearTimeout,
    matchMedia: () => ({
      matches: metrics.reducedMotion,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
    getComputedStyle: () => ({}),
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
    ResizeObserver: TestResizeObserver,
  });
  return document;
}

async function mountCapture(props: CaptureSceneProps, strict = false) {
  const React = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { CaptureScene } = await import("./CaptureScene");
  const document = globalThis.document as unknown as TestDocument;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container as unknown as Element);
  await React.act(async () => {
    root.render(strict
      ? <React.StrictMode><CaptureScene {...props} /></React.StrictMode>
      : <CaptureScene {...props} />);
  });
  return { React, root, container };
}

describe("CaptureScene mounted lifecycle", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resizeCallbacks = [];
    Object.assign(metrics, {
      imagesReady: false,
      stageWidth: 0,
      stageHeight: 0,
      virusWidth: 0,
      virusHeight: 0,
      targetWidth: 0,
      targetHeight: 0,
      reducedMotion: false,
    });
    installDom();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stays hidden and starts no timer before load, then handles zero to positive layout", async () => {
    const onComplete = vi.fn();
    const mounted = await mountCapture({ mode: "animation", onComplete });
    const stage = findByClass(mounted.container, "immune-capture-stage")!;
    expect(stage.getAttribute("data-layout-ready")).toBe("false");
    await vi.advanceTimersByTimeAsync(3_000);
    expect(onComplete).not.toHaveBeenCalled();

    Object.assign(metrics, {
      imagesReady: true,
      stageWidth: 480,
      stageHeight: 270,
      virusWidth: 96,
      virusHeight: 96,
      targetWidth: 160,
      targetHeight: 160,
    });
    await mounted.React.act(async () => resizeCallbacks.forEach((callback) => callback()));
    expect(stage.getAttribute("data-layout-ready")).toBe("true");
    await vi.advanceTimersByTimeAsync(2_399);
    expect(onComplete).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(onComplete).toHaveBeenCalledOnce();
    await mounted.React.act(async () => mounted.root.unmount());
  });

  it("publishes cached dimensions on first display and uses the reduced-motion duration", async () => {
    Object.assign(metrics, {
      imagesReady: true,
      stageWidth: 480,
      stageHeight: 270,
      virusWidth: 96,
      virusHeight: 96,
      targetWidth: 160,
      targetHeight: 160,
      reducedMotion: true,
    });
    const onComplete = vi.fn();
    const mounted = await mountCapture({ mode: "animation", onComplete }, true);
    expect(findByClass(mounted.container, "immune-capture-stage")!.getAttribute("data-layout-ready"))
      .toBe("true");
    await vi.advanceTimersByTimeAsync(49);
    expect(onComplete).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(onComplete).toHaveBeenCalledOnce();
    await mounted.React.act(async () => mounted.root.unmount());
  });

  it("waits for fallback layout after video error and ignores callbacks after renderer switch/unmount", async () => {
    const onComplete = vi.fn();
    const mounted = await mountCapture({ mode: "video", videoSrc: "broken.mp4", onComplete });
    const video = findByClass(mounted.container, "immune-capture-video")!;
    await mounted.React.act(async () => video.dispatchEvent({ type: "error" }));
    expect(findByClass(mounted.container, "immune-capture-stage")!.getAttribute("data-layout-ready"))
      .toBe("false");
    await vi.advanceTimersByTimeAsync(3_000);
    expect(onComplete).not.toHaveBeenCalled();

    Object.assign(metrics, {
      imagesReady: true,
      stageWidth: 480,
      stageHeight: 270,
      virusWidth: 96,
      virusHeight: 96,
      targetWidth: 160,
      targetHeight: 160,
    });
    await mounted.React.act(async () => resizeCallbacks.forEach((callback) => callback()));
    await mounted.React.act(async () => mounted.root.unmount());
    resizeCallbacks.forEach((callback) => callback());
    await vi.advanceTimersByTimeAsync(3_000);
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("cancels animation work across renderer changes and makes queued load/resize callbacks no-op", async () => {
    Object.assign(metrics, {
      imagesReady: true,
      stageWidth: 480,
      stageHeight: 270,
      virusWidth: 96,
      virusHeight: 96,
      targetWidth: 160,
      targetHeight: 160,
    });
    const onComplete = vi.fn();
    const mounted = await mountCapture({ mode: "animation", onComplete });
    const staleVirus = findByClass(mounted.container, "immune-capture-virus")!;
    const staleResizeCallbacks = [...resizeCallbacks];
    const { CaptureScene } = await import("./CaptureScene");

    await mounted.React.act(async () => mounted.root.render(
      <CaptureScene mode="video" videoSrc="capture.mp4" onComplete={onComplete} />,
    ));
    staleResizeCallbacks.forEach((callback) => callback());
    staleVirus.dispatchEvent({ type: "load" });
    await vi.advanceTimersByTimeAsync(3_000);
    expect(onComplete).not.toHaveBeenCalled();

    await mounted.React.act(async () => mounted.root.unmount());
    staleResizeCallbacks.forEach((callback) => callback());
    staleVirus.dispatchEvent({ type: "load" });
    await vi.advanceTimersByTimeAsync(3_000);
    expect(onComplete).not.toHaveBeenCalled();
  });
});
