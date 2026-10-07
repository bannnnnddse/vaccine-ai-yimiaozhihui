import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { InteractiveDemoModal } from "../InteractiveDemoModal";
import {
  ImmuneExperienceModal,
  completeLevelTwoStage,
  startLevelTwoStage,
} from "./ImmuneExperienceModal";

const modalSource = readFileSync(new URL("./ImmuneExperienceModal.tsx", import.meta.url), "utf8");

describe("ImmuneExperienceModal stage helpers", () => {
  it("connects the science action to level two and notifies the external observer once", () => {
    const setStage = vi.fn();
    const notify = vi.fn();

    startLevelTwoStage(setStage, notify);

    expect(setStage).toHaveBeenCalledExactlyOnceWith("level-two");
    expect(notify).toHaveBeenCalledOnce();
  });

  it("moves level-two completion directly to level three", () => {
    const setStage = vi.fn();

    completeLevelTwoStage(setStage);

    expect(setStage).toHaveBeenCalledExactlyOnceWith("level-three");
  });
});

describe("ImmuneExperienceModal markup", () => {
  it("renders the embedded experience without a close control", () => {
    const markup = renderToStaticMarkup(<ImmuneExperienceModal open embedded onClose={() => undefined} />);
    expect(markup).toContain('role="region"');
    expect(markup).not.toContain("immune-modal-close");
    expect(markup).not.toContain("退出免疫科普体验");
    expect(markup).not.toContain("退出后将保留当前已完成进度");
    expect(markup).toContain(">开始</button>");
  });

  it("renders an accessible dialog with LevelOne and the medical boundary", () => {
    const markup = renderToStaticMarkup(
      <ImmuneExperienceModal open onClose={() => undefined} />,
    );

    expect(markup).toContain('role="dialog"');
    expect(markup).toContain('aria-modal="true"');
    expect(markup).toContain('aria-labelledby="immune-experience-title"');
    expect(markup).toContain('id="immune-experience-title"');
    expect(markup).toContain('tabindex="-1"');
    expect(markup).toContain(">开始</button>");
    expect(markup).not.toContain('class="immune-modal-disclaimer"');
  });

  it("renders nothing while closed", () => {
    expect(renderToStaticMarkup(
      <ImmuneExperienceModal open={false} onClose={() => undefined} />,
    )).toBe("");
  });

  it("wires the tested stage helpers into the three production branches", () => {
    expect(modalSource).toContain("startLevelTwoStage(setExperienceStage, onStartLevelTwo)");
    expect(modalSource).toContain("completeLevelTwoStage(setExperienceStage)");
    expect(modalSource).toContain('experienceStage === "level-one"');
    expect(modalSource).toContain('experienceStage === "level-two"');
    expect(modalSource).toContain('experienceStage === "level-three"');
    expect(modalSource).toContain("<LevelTwo onComplete={handleLevelTwoComplete} />");
    expect(modalSource).toContain("<LevelThree onEnter={onStartLevelThree} />");
  });
});

describe("InteractiveDemoModal compatibility entry", () => {
  it("accepts only the lightweight modal contract and renders LevelOne", () => {
    const markup = renderToStaticMarkup(
      <InteractiveDemoModal open onClose={() => undefined} />,
    );

    expect(markup).toContain('class="immune-modal"');
    expect(markup).toContain(">开始</button>");
  });
});
