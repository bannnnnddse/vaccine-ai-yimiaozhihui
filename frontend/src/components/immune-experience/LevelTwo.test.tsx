import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { LevelTwo } from "./LevelTwo";

const source = readFileSync(new URL("./LevelTwo.tsx", import.meta.url), "utf8");

describe("LevelTwo", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts on the real video scene", () => {
    const markup = renderToStaticMarkup(<LevelTwo onComplete={() => undefined} />);

    expect(markup).toContain("immune-level-two-video-scene");
  });

  it("wires the video handoff, quiz answer, feedback runtime, and cancel cleanup", () => {
    expect(source).toContain('transitioning={state.phase === "video-transition"}');
    expect(source).toContain('onEnded={() => dispatch({ type: "video-ended" })}');
    expect(source).toContain('createLevelTwoTransitionRuntime');
    expect(source).toContain('type: "video-transition-finished"');
    expect(source).toContain('state.phase === "video" || state.phase === "video-transition"');
    expect(source).toContain("<AntigenPresentationQuiz");
    expect(source).toContain("onAnswer={handleAnswer}");
    expect(source).toContain('runtimeRef.current?.start(answer === "A" ? "correct" : "incorrect")');
    expect(source).toContain("runtimeRef.current?.cancel();");
    expect(source).toContain("transitionRuntimeRef.current?.cancel();");
  });
});
