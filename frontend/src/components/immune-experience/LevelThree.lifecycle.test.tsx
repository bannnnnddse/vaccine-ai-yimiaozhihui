import { act } from "react";
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
  documentElement: TestNode;
  body: TestNode;
  defaultView: Record<string, unknown> | null = null;

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

const reducedMotion = vi.hoisted(() => ({ value: false }));

vi.mock("./useReducedMotion", () => ({
  useReducedMotion: () => reducedMotion.value,
}));

vi.mock("./LymphScene", () => ({
  LymphScene: (props: {
    phase: string;
    onSelectCell: (cellId: "helper-t-cell") => void;
    onContactContinue?: () => void;
    exitingActivationCaption?: string | null;
  }) => (
    <div data-testid="scene" data-phase={props.phase} data-exiting-caption={props.exitingActivationCaption ?? ""}>
      <button data-testid="select-helper" onClick={() => props.onSelectCell("helper-t-cell")} />
      <button data-testid="continue-contact" onClick={props.onContactContinue} />
    </div>
  ),
}));

import { LevelThree } from "./LevelThree";

function installDom() {
  const document = new TestDocument();
  const window = {
    document,
    Node: TestNode,
    Element: TestNode,
    HTMLElement: TestNode,
    HTMLIFrameElement: class extends TestNode {},
    setTimeout,
    clearTimeout,
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

describe("LevelThree contact timing", () => {
  let root: Root;
  let container: TestNode;

  beforeEach(async () => {
    vi.useFakeTimers();
    reducedMotion.value = false;
    const document = installDom();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container as unknown as Element);
    await act(async () => root.render(<LevelThree />));
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    expect(vi.getTimerCount()).toBe(0);
    vi.useRealTimers();
  });

  const phase = () => findByTestId(container, "scene").getAttribute("data-phase");
  const exitingCaption = () => findByTestId(container, "scene").getAttribute("data-exiting-caption");
  const advance = async (duration: number) => {
    await act(async () => { await vi.advanceTimersByTimeAsync(duration); });
  };
  const click = async (testId: string) => {
    await act(async () => findByTestId(container, testId).dispatchEvent({ type: "click" }));
  };
  const reachContact = async () => {
    await click("select-helper");
    await advance(1_400);
    await advance(700);
  };

  it("fades and advances each caption scene after eight seconds", async () => {
    await reachContact();
    expect(phase()).toBe("t-cell-contact");

    await advance(1_800);
    expect(phase()).toBe("t-cell-contact-hold");
    await advance(5_799);
    expect(phase()).toBe("t-cell-contact-hold");
    await advance(1);
    expect(exitingCaption()).toBe("contact");
    await advance(399);
    expect(phase()).toBe("t-cell-contact-hold");
    await advance(1);
    expect(phase()).toBe("antigen-presentation");

    await advance(1_600);
    expect(phase()).toBe("antigen-presentation-hold");
    await advance(5_999);
    expect(exitingCaption()).toBe("");
    await advance(1);
    expect(exitingCaption()).toBe("helper-to-b");
    await advance(400);
    expect(phase()).toBe("b-cell-patrol-intro");
  });

  it("fades and advances either caption scene when the user clicks", async () => {
    await reachContact();
    await click("continue-contact");
    expect(exitingCaption()).toBe("contact");
    await advance(399);
    expect(phase()).toBe("t-cell-contact");
    await advance(1);
    expect(phase()).toBe("antigen-presentation");

    await click("continue-contact");
    expect(exitingCaption()).toBe("helper-to-b");
    await advance(400);
    expect(phase()).toBe("b-cell-patrol-intro");
  });

  it("skips motion under reduced motion but preserves each eight-second scene", async () => {
    reducedMotion.value = true;
    await act(async () => root.render(<LevelThree />));
    await reachContact();
    expect(phase()).toBe("t-cell-contact-hold");

    await advance(7_999);
    expect(phase()).toBe("t-cell-contact-hold");
    await advance(1);
    expect(phase()).toBe("antigen-presentation-hold");
    await advance(7_999);
    expect(phase()).toBe("antigen-presentation-hold");
    await advance(1);
    expect(phase()).toBe("b-cell-patrol-intro");
  });
});
