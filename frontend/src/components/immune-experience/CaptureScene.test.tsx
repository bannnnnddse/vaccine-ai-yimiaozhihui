import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { immuneAssets } from "../../assets/immune/immuneAssets";
import {
  CAPTURE_DURATION_MS,
  CAPTURE_PHASES,
  CAPTURE_VIRUS_ASPECT_RATIO,
  CAPTURE_VIRUS_KEYFRAMES,
  CaptureScene,
  clampCapturePosition,
  clampCaptureTargetPosition,
  createCaptureRuntime,
  createCaptureLayoutRuntime,
  getCaptureDuration,
  getFallbackVirusSize,
  getCaptureVirusAabb,
  getCaptureRenderer,
  scaleCapturePointToStage,
  REDUCED_CAPTURE_DURATION_MS,
  measureCaptureLayout,
} from "./CaptureScene";

describe("CaptureScene", () => {
  it.each([
    ["animation", "capture.mp4", false, "animation"],
    ["video", undefined, false, "animation"],
    ["video", "capture.mp4", false, "video"],
    ["video", "capture.mp4", true, "animation"],
  ] as const)(
    "selects %s with source %s and videoFailed %s as %s",
    (mode, videoSrc, videoFailed, expected) => {
      expect(getCaptureRenderer(mode, videoSrc, videoFailed)).toBe(expected);
    },
  );

  it("renders the approved animation assets at the supplied position", () => {
    const markup = renderToStaticMarkup(
      <CaptureScene
        mode="animation"
        captureSnapshot={{
          virusPosition: { x: 148, y: 96 },
          targetCenter: { x: 356, y: 172 },
          stageSize: { width: 640, height: 360 },
        }}
        onComplete={() => undefined}
      />,
    );

    expect(markup).toContain(immuneAssets.tissueBackground);
    expect(markup).toContain(immuneAssets.virusNervous);
    expect(markup).toContain(immuneAssets.dendriticCell);
    expect(markup).toContain('data-layout-ready="false"');
    expect(markup).not.toContain("--immune-capture-virus-x:");
    expect(markup).not.toContain("--immune-capture-target-x:");
    expect(markup).not.toContain("<video");
    expect(markup).toMatch(/immune-capture-stage[\s\S]*immune-capture-status[\s\S]*<\/div><\/section>/);
    expect(markup).not.toContain("immune-medical-note");
  });

  it("renders video only when video mode has a source", () => {
    const markup = renderToStaticMarkup(
      <CaptureScene mode="video" videoSrc="capture.mp4" onComplete={() => undefined} />,
    );

    expect(markup).toContain("<video");
    expect(markup).toContain('src="capture.mp4"');
    expect(markup).not.toContain(immuneAssets.virusNervous);
  });

  it("clamps the complete nervous animation envelope inside a resized stage", () => {
    const bottomRight = clampCapturePosition(
      { x: 620, y: -20 },
      { width: 480, height: 300 },
      { width: 96, height: 84 },
    );
    expect(bottomRight.x).toBeCloseTo(379.0578268272);
    expect(bottomRight.y).toBeCloseTo(2.2130946708);

    const topLeft = clampCapturePosition(
      { x: -100, y: -100 },
      { width: 480, height: 300 },
      { width: 96, height: 84 },
    );
    expect(topLeft.x).toBeCloseTo(5.9309039440);
    expect(topLeft.y).toBeCloseTo(2.2130946708);

    const normal = clampCapturePosition(
      { x: 120, y: 90 },
      { width: 480, height: 300 },
      { width: 96, height: 84 },
    );
    expect(normal).toEqual({ x: 120, y: 90 });
  });

  it("keeps every rotated, translated, and scaled keyframe AABB inside all four stage edges", () => {
    const stage = { width: 480, height: 300 };
    const virus = { width: 96, height: 84 };

    for (const requested of [{ x: -100, y: -100 }, { x: 620, y: 500 }]) {
      const position = clampCapturePosition(requested, stage, virus);
      for (const frame of CAPTURE_VIRUS_KEYFRAMES) {
        const box = getCaptureVirusAabb(position, virus, frame);
        expect(box.left).toBeGreaterThanOrEqual(0);
        expect(box.top).toBeGreaterThanOrEqual(0);
        expect(box.right).toBeLessThanOrEqual(stage.width);
        expect(box.bottom).toBeLessThanOrEqual(stage.height);
      }
    }
  });

  it("shrinks an oversized virus proportionally before clamping it in an extremely small stage", () => {
    const layout = measureCaptureLayout(
      { clientWidth: 8, clientHeight: 6 },
      { offsetWidth: 132, offsetHeight: 99, complete: true, naturalWidth: 1024 },
      { offsetWidth: 12, offsetHeight: 12, complete: true, naturalWidth: 160 },
      {
        virusPosition: { x: 620, y: -20 },
        targetCenter: { x: 12, y: 9 },
        stageSize: { width: 640, height: 360 },
      },
    );

    expect(layout).not.toBeNull();
    expect(layout!.virusSize.width / layout!.virusSize.height).toBeCloseTo(4 / 3);
    expect(layout!.virusSize.width).toBeGreaterThan(0);
    expect(layout!.virusSize.height).toBeGreaterThan(0);
    for (const value of [
      layout!.virusPosition.x,
      layout!.virusPosition.y,
      layout!.virusSize.width,
      layout!.virusSize.height,
    ]) expect(Number.isFinite(value)).toBe(true);
    for (const frame of CAPTURE_VIRUS_KEYFRAMES) {
      const box = getCaptureVirusAabb(
        layout!.virusPosition,
        layout!.virusSize,
        frame,
        layout!.virusMotionScale,
      );
      expect(box.left).toBeGreaterThanOrEqual(-1e-7);
      expect(box.top).toBeGreaterThanOrEqual(-1e-7);
      expect(box.right).toBeLessThanOrEqual(8 + 1e-7);
      expect(box.bottom).toBeLessThanOrEqual(6 + 1e-7);
    }
  });

  it("never reports layout ready for zero or unreliable element dimensions", () => {
    const snapshot = {
      virusPosition: { x: 148, y: 96 },
      targetCenter: { x: 356, y: 172 },
      stageSize: { width: 640, height: 360 },
    };

    expect(measureCaptureLayout(
      { clientWidth: 0, clientHeight: 360 },
      { offsetWidth: 96, offsetHeight: 96, complete: true, naturalWidth: 1024 },
      { offsetWidth: 160, offsetHeight: 160, complete: true, naturalWidth: 160 },
      snapshot,
    )).toBeNull();
    expect(measureCaptureLayout(
      { clientWidth: 480, clientHeight: 270 },
      { offsetWidth: 0, offsetHeight: 0, complete: true, naturalWidth: 1024 },
      { offsetWidth: 160, offsetHeight: 160, complete: true, naturalWidth: 160 },
      snapshot,
    )).toBeNull();
    expect(measureCaptureLayout(
      { clientWidth: 480, clientHeight: 270 },
      { offsetWidth: 96, offsetHeight: 96, complete: true, naturalWidth: 1024 },
      { offsetWidth: 0, offsetHeight: 0, complete: false, naturalWidth: 0 },
      snapshot,
    )).toBeNull();
  });

  it("maps the collision snapshot before the first layout-ready frame and recalculates on resize", () => {
    const snapshot = {
      virusPosition: { x: 148, y: 96 },
      targetCenter: { x: 356, y: 172 },
      stageSize: { width: 640, height: 360 },
    };
    const first = measureCaptureLayout(
      { clientWidth: 480, clientHeight: 270 },
      { offsetWidth: 96, offsetHeight: 96, complete: true, naturalWidth: 1024 },
      { offsetWidth: 160, offsetHeight: 160, complete: true, naturalWidth: 160 },
      snapshot,
    );
    expect(first).toEqual({
      virusPosition: { x: 111, y: 72 },
      virusSize: { width: 96, height: 96 },
      virusMotionScale: 1,
      targetPosition: { x: 187, y: 49 },
    });

    const resized = measureCaptureLayout(
      { clientWidth: 320, clientHeight: 180 },
      { offsetWidth: 80, offsetHeight: 80, complete: true, naturalWidth: 1024 },
      { offsetWidth: 120, offsetHeight: 120, complete: true, naturalWidth: 160 },
      snapshot,
    );
    expect(resized).toEqual({
      virusPosition: { x: 74, y: 48 },
      virusSize: { width: 80, height: 80 },
      virusMotionScale: 1,
      targetPosition: { x: 118, y: 26 },
    });
  });

  it("stays hidden until image load, then publishes mapped resize layouts and disconnects", () => {
    const stage = { clientWidth: 480, clientHeight: 270 };
    const virus = {
      offsetWidth: 0,
      offsetHeight: 0,
      complete: false,
      naturalWidth: 0,
    };
    const target = {
      offsetWidth: 160,
      offsetHeight: 160,
      complete: true,
      naturalWidth: 160,
    };
    const onLayout = vi.fn();
    const observe = vi.fn();
    const disconnect = vi.fn();
    let resize: () => void = () => undefined;
    const runtime = createCaptureLayoutRuntime({
      stage,
      virus,
      target,
      captureSnapshot: {
        virusPosition: { x: 148, y: 96 },
        targetCenter: { x: 356, y: 172 },
        stageSize: { width: 640, height: 360 },
      },
      onLayout,
      createObserver: (callback) => {
        resize = callback;
        return { observe, disconnect };
      },
    });

    expect(onLayout).toHaveBeenLastCalledWith(null);
    expect(observe).toHaveBeenCalledTimes(3);

    Object.assign(virus, {
      offsetWidth: 96,
      offsetHeight: 96,
      complete: true,
      naturalWidth: 1024,
    });
    runtime.recalculate();
    expect(onLayout).toHaveBeenLastCalledWith({
      virusPosition: { x: 111, y: 72 },
      virusSize: { width: 96, height: 96 },
      virusMotionScale: 1,
      targetPosition: { x: 187, y: 49 },
    });

    stage.clientWidth = 320;
    stage.clientHeight = 180;
    resize();
    const resizedLayout = onLayout.mock.lastCall?.[0];
    expect(resizedLayout).toMatchObject({
      virusPosition: { x: 74, y: 48 },
      virusSize: { width: 96, height: 96 },
      targetPosition: { x: 98 },
    });
    expect(resizedLayout?.targetPosition.y).toBeCloseTo(11.2);

    runtime.dispose();
    expect(disconnect).toHaveBeenCalledOnce();

    onLayout.mockClear();
    runtime.recalculate();
    resize();
    expect(onLayout).not.toHaveBeenCalled();
  });

  it("centers the dendritic cell on the collision point and clamps its edges", () => {
    expect(clampCaptureTargetPosition(
      { x: 240, y: 150 },
      { width: 480, height: 300 },
      { width: 120, height: 100 },
    )).toEqual({ x: 180, y: 100 });
    const edgePosition = clampCaptureTargetPosition(
      { x: 470, y: -12 },
      { width: 480, height: 300 },
      { width: 120, height: 100 },
    );
    expect(edgePosition.x).toBeCloseTo(351.6);
    expect(edgePosition.y).toBeCloseTo(7);
  });

  it("keeps the same relative collision point after the stage resizes", () => {
    expect(scaleCapturePointToStage(
      { x: 480, y: 90 },
      { width: 640, height: 360 },
      { width: 320, height: 720 },
    )).toEqual({ x: 240, y: 180 });
  });

  it("keeps the replacement virus square when a fallback size is needed", () => {
    expect(CAPTURE_VIRUS_ASPECT_RATIO).toBe(1);
    expect(getFallbackVirusSize(112)).toEqual({ width: 112, height: 112 });
  });

  it("defines ordered non-overlapping visual phases", () => {
    expect(CAPTURE_PHASES).toEqual({
      nervousEnd: 20,
      dendriticEnd: 50,
      virusEnd: 78,
      backgroundEnd: 100,
    });
  });

  it("uses 2400ms normally and 50ms for reduced motion", () => {
    expect(CAPTURE_DURATION_MS).toBe(2_400);
    expect(REDUCED_CAPTURE_DURATION_MS).toBe(50);
    expect(getCaptureDuration(false)).toBe(2_400);
    expect(getCaptureDuration(true)).toBe(50);
  });

  it("uses one animation timer and clears it during cleanup", () => {
    const clearTimer = vi.fn();
    const setTimer = vi.fn(() => 29);
    const runtime = createCaptureRuntime({
      onComplete: vi.fn(),
      setTimer,
      clearTimer,
    });

    runtime.dispatch({ type: "start-animation", delay: 2_400 });
    runtime.dispatch({ type: "cancel" });

    expect(setTimer).toHaveBeenCalledOnce();
    expect(setTimer).toHaveBeenCalledWith(expect.any(Function), 2_400);
    expect(clearTimer).toHaveBeenCalledOnce();
    expect(clearTimer).toHaveBeenCalledWith(29);
  });

  it("does not complete when a cleared callback races with cleanup", () => {
    const onComplete = vi.fn();
    let timerCallback = () => undefined;
    const runtime = createCaptureRuntime({
      onComplete,
      setTimer: vi.fn((callback) => {
        timerCallback = callback;
        return 31;
      }),
      clearTimer: vi.fn(),
    });

    runtime.dispatch({ type: "start-animation", delay: 2_400 });
    runtime.dispatch({ type: "cancel" });
    timerCallback();

    expect(onComplete).not.toHaveBeenCalled();
  });

  it("cancels an animation timer when switching to video without settling the gate", () => {
    const onComplete = vi.fn();
    const clearTimer = vi.fn();
    let oldTimerCallback = () => undefined;
    const runtime = createCaptureRuntime({
      onComplete,
      setTimer: vi.fn((callback) => {
        oldTimerCallback = callback;
        return 35;
      }),
      clearTimer,
    });

    runtime.dispatch({ type: "start-animation", delay: 2_400 });
    runtime.dispatch({ type: "cancel-animation" });
    oldTimerCallback();

    expect(onComplete).not.toHaveBeenCalled();
    expect(clearTimer).toHaveBeenCalledOnce();
    expect(clearTimer).toHaveBeenCalledWith(35);

    runtime.dispatch({ type: "complete" });
    runtime.dispatch({ type: "complete" });

    expect(onComplete).toHaveBeenCalledOnce();
  });

  it("switches from video error once and starts only one animation timer", () => {
    const setTimer = vi.fn(() => 37);
    const runtime = createCaptureRuntime({
      onComplete: vi.fn(),
      setTimer,
      clearTimer: vi.fn(),
    });

    expect(runtime.dispatch({ type: "video-error" })).toBe(true);
    expect(runtime.dispatch({ type: "video-error" })).toBe(false);
    expect(setTimer).not.toHaveBeenCalled();
    runtime.dispatch({ type: "start-animation", delay: 2_400 });

    expect(setTimer).toHaveBeenCalledOnce();
  });

  it("completes once when video ended, error fallback, and timer race", () => {
    const onComplete = vi.fn();
    const clearTimer = vi.fn();
    let timerCallback = () => undefined;
    const runtime = createCaptureRuntime({
      onComplete,
      setTimer: vi.fn((callback) => {
        timerCallback = callback;
        return 41;
      }),
      clearTimer,
    });

    runtime.dispatch({ type: "video-error" });
    runtime.dispatch({ type: "start-animation", delay: 2_400 });
    runtime.dispatch({ type: "complete" });
    runtime.dispatch({ type: "video-error" });
    timerCallback();

    expect(onComplete).toHaveBeenCalledOnce();
    expect(clearTimer).toHaveBeenCalledOnce();
    expect(clearTimer).toHaveBeenCalledWith(41);
  });

  it("updates the parent callback without rebuilding the completion gate", () => {
    const firstOnComplete = vi.fn();
    const latestOnComplete = vi.fn();
    let timerCallback = () => undefined;
    const runtime = createCaptureRuntime({
      onComplete: firstOnComplete,
      setTimer: vi.fn((callback) => {
        timerCallback = callback;
        return 43;
      }),
      clearTimer: vi.fn(),
    });

    expect(runtime.updateOnComplete(latestOnComplete)).toBe(runtime);
    runtime.dispatch({ type: "start-animation", delay: 2_400 });
    timerCallback();

    expect(firstOnComplete).not.toHaveBeenCalled();
    expect(latestOnComplete).toHaveBeenCalledOnce();
  });
});
