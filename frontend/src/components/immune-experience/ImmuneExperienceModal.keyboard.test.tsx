import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ImmuneExperienceModal } from "./ImmuneExperienceModal";

const effects = vi.hoisted(() => ({ callbacks: [] as (() => void | (() => void))[] }));
vi.mock("react", async (importOriginal) => ({
  ...await importOriginal<typeof import("react")>(),
  useEffect: (callback: () => void | (() => void)) => effects.callbacks.push(callback),
}));
vi.mock("./LevelOne", () => ({ LevelOne: () => <button>Start fixture</button> }));
vi.mock("./LevelTwo", () => ({ LevelTwo: () => null }));
vi.mock("./LevelThree", () => ({ LevelThree: () => null }));

let target: EventTarget;
let cleanups: (() => void)[];
function mount(open: boolean, onClose = vi.fn()) {
  renderToStaticMarkup(<ImmuneExperienceModal open={open} onClose={onClose} />);
  cleanups = effects.callbacks.map((callback) => callback()).filter(
    (cleanup): cleanup is () => void => typeof cleanup === "function",
  );
}
function key(key: string, shiftKey = false) {
  const event = Object.assign(new Event("keydown", { cancelable: true }), { key, shiftKey });
  target.dispatchEvent(event);
  return event;
}
beforeEach(() => {
  effects.callbacks = [];
  cleanups = [];
  target = new EventTarget();
  vi.stubGlobal("window", target);
});
afterEach(() => { cleanups.forEach((cleanup) => cleanup()); vi.unstubAllGlobals(); });

describe("production interactive keyboard behavior", () => {
  it("leaves Tab and Shift+Tab available for native focus navigation", () => {
    const onClose = vi.fn();
    const advance = vi.fn();
    target.addEventListener("immune-experience:developer-advance", advance);
    mount(true, onClose);
    expect(key("Tab").defaultPrevented).toBe(false);
    expect(key("Tab", true).defaultPrevented).toBe(false);
    expect(advance).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
  it("retains Escape dismissal and removes the listener on cleanup", () => {
    const onClose = vi.fn();
    mount(true, onClose);
    expect(key("Escape").defaultPrevented).toBe(true);
    expect(onClose).toHaveBeenCalledOnce();
    cleanups.forEach((cleanup) => cleanup());
    expect(key("Escape").defaultPrevented).toBe(false);
    expect(onClose).toHaveBeenCalledOnce();
  });
  it("does not intercept keys while closed", () => {
    const onClose = vi.fn();
    mount(false, onClose);
    expect(key("Tab").defaultPrevented).toBe(false);
    expect(key("Escape").defaultPrevented).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
  });
});
