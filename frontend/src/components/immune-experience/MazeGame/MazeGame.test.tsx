import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { MAZE_INTRO_HOLD_DURATION_MS, MazeGame, type MazeCaptureSnapshot } from "./MazeGame";

const styles = readFileSync(new URL("../../../styles.css", import.meta.url), "utf8");

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
  rect = { width: 0, height: 0 };

  constructor(tagName: string, ownerDocument: TestDocument) {
    this.tagName = tagName.toUpperCase();
    this.nodeName = this.tagName;
    this.ownerDocument = ownerDocument;
  }

  get firstChild() { return this.childNodes[0] ?? null; }
  get textContent(): string { return this.childNodes.map((child) => child.textContent).join(""); }
  set textContent(value: string) { this.childNodes = value ? [this.ownerDocument.createTextNode(value)] : []; }
  getAttribute(name: string) { return this.attributes.get(name) ?? null; }
  setAttribute(name: string, value: unknown) { this.attributes.set(name, String(value)); }
  removeAttribute(name: string) { this.attributes.delete(name); }
  hasAttribute(name: string) { return this.attributes.has(name); }
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
  querySelector(selector: string): TestNode | null {
    if (selector.startsWith(".") && this.getAttribute("class")?.split(" ").includes(selector.slice(1))) {
      return this;
    }
    for (const child of this.childNodes) {
      const match = child.querySelector(selector);
      if (match) return match;
    }
    return null;
  }
  getBoundingClientRect() {
    return { ...this.rect, top: 0, right: this.rect.width, bottom: this.rect.height, left: 0, x: 0, y: 0, toJSON: () => ({}) };
  }
  focus() { this.ownerDocument.activeElement = this; }
}

class TestTextNode extends TestNode {
  override nodeType = 3;
  constructor(private data: string, ownerDocument: TestDocument) {
    super("#text", ownerDocument);
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

interface TestEvent {
  type: string;
  clientX?: number;
  clientY?: number;
  key?: string;
  target?: TestNode;
  currentTarget?: TestNode;
  preventDefault?: () => void;
}

function installDom(prefersReducedMotion = false) {
  const document = new TestDocument();
  const window = {
    document,
    Node: TestNode,
    Element: TestNode,
    HTMLElement: TestNode,
    HTMLIFrameElement: class extends TestNode {},
    setTimeout,
    clearTimeout,
    matchMedia: () => ({
      matches: prefersReducedMotion,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
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

function findByAttribute(root: TestNode, name: string, value?: string): TestNode {
  if (root.getAttribute(name) !== null && (value === undefined || root.getAttribute(name) === value)) return root;
  for (const child of root.childNodes) {
    try { return findByAttribute(child, name, value); } catch { /* keep searching */ }
  }
  throw new Error(`Missing [${name}${value === undefined ? "" : `=${value}`}]`);
}

function gameRoot(container: TestNode) { return findByAttribute(container, "role", "application"); }
function virus(container: TestNode) { return findByAttribute(container, "data-maze-virus"); }
function mazeCanvas(container: TestNode) { return findByAttribute(container, "data-maze-columns", "21"); }
function status(container: TestNode) { return findByAttribute(container, "role", "status"); }

async function keyDown(container: TestNode, key: string) {
  await act(async () => {
    gameRoot(container).dispatchEvent({ type: "keydown", key, preventDefault: () => undefined });
  });
}

async function swipe(container: TestNode, from: { x: number; y: number }, to: { x: number; y: number }) {
  await act(async () => {
    const game = gameRoot(container);
    game.dispatchEvent({ type: "pointerdown", clientX: from.x, clientY: from.y });
    game.dispatchEvent({ type: "pointerup", clientX: to.x, clientY: to.y });
  });
}

describe("MazeGame", () => {
  let root: Root;
  let container: TestNode;
  let onCapture: ReturnType<typeof vi.fn<(snapshot: MazeCaptureSnapshot) => void>>;

  async function mount(prefersReducedMotion = false) {
    const document = installDom(prefersReducedMotion);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    onCapture = vi.fn<(snapshot: MazeCaptureSnapshot) => void>();
    await act(async () => root.render(<MazeGame onCapture={onCapture} />));
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(async () => {
    await act(async () => root?.unmount());
    vi.useRealTimers();
  });

  it("moves from keyboard and only accepts swipes whose dominant axis reaches 24 pixels", async () => {
    await mount();

    await swipe(container, { x: 0, y: 0 }, { x: 20, y: 20 });
    expect(virus(container).getAttribute("data-maze-node")).toBe("r2c1");
    expect(status(container).textContent).toContain("至少 24 像素");

    await swipe(container, { x: 0, y: 0 }, { x: 23, y: 24 });
    expect(virus(container).getAttribute("data-maze-node")).toBe("r5c1");

    await keyDown(container, "ArrowRight");
    expect(virus(container).getAttribute("data-maze-node")).toBe("r5c3");
    expect((gameRoot(container).style as unknown as { touchAction?: string }).touchAction).toBe("none");
  });

  it("focuses the maze application when the scene mounts so keyboard input works immediately", async () => {
    await mount();

    expect(container.ownerDocument.activeElement).toBe(gameRoot(container));
    await keyDown(container, "s");
    expect(virus(container).getAttribute("data-maze-node")).toBe("r5c1");
  });

  it("keeps both opening instructions visible for thirty seconds", async () => {
    await mount();
    expect(MAZE_INTRO_HOLD_DURATION_MS).toBe(30_000);
    expect(findByAttribute(container, "data-maze-intro", "visible").textContent).toContain("通过↑↓←→ / WASD操控病毒颗粒");
    expect(findByAttribute(container, "data-maze-intro", "visible").textContent).toContain("躲避树突状细胞的追击！");

    await act(async () => { await vi.advanceTimersByTimeAsync(29_999); });
    expect(findByAttribute(container, "data-maze-intro", "visible")).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(findByAttribute(container, "data-maze-intro", "leaving")).toBeTruthy();
  });

  it("centers the opening instructions inside a translucent white bubble", () => {
    const introRule = styles.match(/\.immune-maze__intro\s*{([^}]*)}/s)?.[1] ?? "";

    expect(introRule).toContain("top: 50%");
    expect(introRule).toContain("left: 50%");
    expect(introRule).toMatch(/background:\s*rgba\(255,255,255,\.82\)/);
    expect(introRule).toMatch(/border-radius:\s*clamp\(/);
    expect(introRule).toContain("backdrop-filter: blur(16px)");
  });

  it("dismisses the opening instructions immediately on player input", async () => {
    await mount();
    await keyDown(container, "ArrowDown");
    expect(findByAttribute(container, "data-maze-intro", "leaving")).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(360); });
    expect(() => findByAttribute(container, "data-maze-intro")).toThrow();
  });

  it("starts the pursuit runtime once after the first valid move and announces the live state", async () => {
    await mount();

    await keyDown(container, "ArrowDown");
    expect(gameRoot(container).getAttribute("data-pursuit-phase")).toBe("waiting");
    expect(status(container).textContent).toContain("正在锁定病毒");
    expect(vi.getTimerCount()).toBeGreaterThanOrEqual(2);

    await keyDown(container, "ArrowRight");
    expect(vi.getTimerCount()).toBeGreaterThanOrEqual(2);
  });

  it("captures immediately when a player slide crosses the dendritic cell path node", async () => {
    await mount();
    mazeCanvas(container).rect = { width: 420, height: 260 };

    await keyDown(container, "ArrowUp");

    expect(virus(container).getAttribute("data-maze-node")).toBe("r1c1");
    expect(gameRoot(container).getAttribute("data-pursuit-phase")).toBe("captured");
    expect(vi.getTimerCount()).toBeGreaterThanOrEqual(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    expect(onCapture).toHaveBeenCalledOnce();
    expect(onCapture.mock.calls[0][0].targetCenter).toEqual({ x: 30, y: 30 });
  });

  it("captures once, freezes later input, and snapshots the maze canvas instead of its outer shell", async () => {
    await mount();
    gameRoot(container).rect = { width: 1000, height: 800 };
    mazeCanvas(container).rect = { width: 420, height: 260 };

    await keyDown(container, "ArrowDown");
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });

    expect(gameRoot(container).getAttribute("data-pursuit-phase")).toBe("captured");
    expect(gameRoot(container).getAttribute("data-capture-animation")).toBe("playing");
    expect(onCapture).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(onCapture).toHaveBeenCalledWith({
      virusPosition: { x: 23.6, y: 103.6 },
      targetCenter: { x: 30, y: 110 },
      stageSize: { width: 420, height: 260 },
    });
    expect(status(container).textContent).toContain("已捕获病毒");

    await keyDown(container, "ArrowRight");
    expect(virus(container).getAttribute("data-maze-node")).toBe("r5c1");
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(onCapture).toHaveBeenCalledTimes(1);
  });

  it("keeps pursuit active when reduced motion is preferred", async () => {
    await mount(true);

    await keyDown(container, "s");
    expect(gameRoot(container).getAttribute("data-reduced-motion")).toBe("true");
    expect(gameRoot(container).getAttribute("data-pursuit-phase")).toBe("waiting");
    expect(vi.getTimerCount()).toBeGreaterThanOrEqual(2);
  });
});
