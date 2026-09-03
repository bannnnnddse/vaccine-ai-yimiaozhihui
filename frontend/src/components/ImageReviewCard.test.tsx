import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  ImageReviewCard,
  normalizedBBoxToNaturalPixels,
  normalizedDragBBox,
  normalizedPointInImage,
} from "./ImageReviewCard";
import type { EditScopeGuardResult } from "../services/generationService";

const baseProps = {
  imageUrl: "/api/v1/generated-images/job-v1.png",
  imageId: "job-v1",
  stage: "awaiting_human_feedback" as const,
  autoRevisionCount: 1,
  onAccept: () => undefined,
  onEdit: () => undefined,
};

const collateralGuard = {
  passed: false,
  outsideChangeScore: 0.2,
  threshold: 0.05,
  changedOutsideBBox: true,
  insideChangeScore: 0.08,
  minimumInsideChange: 0.01,
  insufficientChangeInsideBBox: false,
  outsideChangeRegions: [[0.75, 0.1, 1, 0.35]],
  notes: "框外变化过大",
} satisfies EditScopeGuardResult;

describe("normalizedDragBBox", () => {
  it("normalizes reverse pointer drags into one authoritative bbox", () => {
    expect(normalizedDragBBox([0.8, 0.7], [0.2, 0.1])).toEqual([0.2, 0.1, 0.8, 0.7]);
  });

  it("ignores click-sized selections", () => {
    expect(normalizedDragBBox([0.2, 0.2], [0.203, 0.8])).toBeNull();
  });
});

describe("ImageReviewCard guard warning", () => {
  it("shows an adopted revision with collateral changes as a manual-review warning", () => {
    const html = renderToStaticMarkup(
      <ImageReviewCard {...baseProps} guardResult={collateralGuard} />,
    );

    expect(html).toContain("已采用修订结果，但框外有其他区域被修改");
    expect(html).toContain("修订图已替换显示");
    expect(html).toContain("检测到框外变化的区域");
    expect(html).toContain("框外变化位置预览（主图不叠加标记）");
    expect(html).not.toContain("候选未被接受");
    expect(html).not.toContain("被拒绝候选");
  });

  it("keeps the rejection warning and comparison when the candidate was not adopted", () => {
    const html = renderToStaticMarkup(
      <ImageReviewCard
        {...baseProps}
        guardResult={collateralGuard}
        candidateImageUrl="/api/v1/generated-images/job-v1-rejected.png"
      />,
    );

    expect(html).toContain("范围保护未通过，候选未被接受");
    expect(html).toContain("被拒绝候选");
    expect(html).not.toContain("已采用修订结果");
  });

  it("keeps trusted pixels primary when a guard-passing candidate fails the critic", () => {
    const html = renderToStaticMarkup(
      <ImageReviewCard
        {...baseProps}
        guardResult={{ ...collateralGuard, passed: true, changedOutsideBBox: false }}
        candidateImageUrl="/api/v1/generated-images/job-v1-rejected.png"
        criticResult={{
          overallStatus: "needs_human_review",
          summary: "未检测到指定标题“流程图”。",
          recommendedAction: "request_human_feedback",
          autoFixable: false,
          humanInputRequired: true,
          issues: [],
        }}
      />,
    );

    expect(html).toContain("局部修改未通过最终视觉审核，可信版本未被覆盖");
    expect(html).toContain("未通过审核的候选");
    expect(html).toContain("未检测到指定标题");
  });

  it("maps CSS-scaled display coordinates to normalized and natural-image coordinates", () => {
    const rect = { left: 100, top: 50, width: 500, height: 250 };
    const start = normalizedPointInImage([150, 75], rect);
    const end = normalizedPointInImage([500, 250], rect);
    const bbox = normalizedDragBBox(start, end);

    expect(bbox).toEqual([0.1, 0.1, 0.8, 0.8]);
    expect(normalizedBBoxToNaturalPixels(bbox!, 2000, 1000)).toEqual([200, 100, 1600, 800]);
  });

  it("offers a one-step restore when a previous version is retained", () => {
    const html = renderToStaticMarkup(
      <ImageReviewCard
        {...baseProps}
        guardResult={collateralGuard}
        previousImageUrl="/api/v1/generated-images/job-v0.png"
        previousImageId="job-v0"
      />,
    );

    expect(html).toContain("恢复上一版");
  });

  it("presents an English critic payload in Chinese without exposing internal type names", () => {
    const html = renderToStaticMarkup(
      <ImageReviewCard
        {...baseProps}
        criticResult={{
          overallStatus: "needs_human_review",
          summary: "The image has a text rendering issue.",
          recommendedAction: "request_human_feedback",
          autoFixable: false,
          humanInputRequired: true,
          issues: [{
            issueType: "text_error", severity: "high", bbox: [0.1, 0.1, 0.3, 0.2], confidence: 0.98,
            description: "The third-step label is incorrectly rendered.",
            suggestedFix: "Replace the erroneous text.",
            observedText: "抗原呈拽", replacementText: "抗原呈递",
            autoFixable: true, humanInputRequired: false,
          }],
        }}
      />,
    );

    expect(html).toContain("AI 审核发现以下需要处理的问题");
    expect(html).toContain("文字标注错误");
    expect(html).toContain("应将“抗原呈拽”修正为“抗原呈递”");
    expect(html).not.toContain("text_error");
    expect(html).not.toContain("The image has a text rendering issue");
  });

  it("renders an accepted result as an image-only card without review, actions, or meta", () => {
    const html = renderToStaticMarkup(
      <ImageReviewCard
        {...baseProps}
        accepted
        previousImageUrl="/api/v1/generated-images/job-v0.png"
        previousImageId="job-v0"
        guardResult={collateralGuard}
        criticResult={{
          overallStatus: "needs_human_review", summary: "需要人工确认", recommendedAction: "request_human_feedback",
          autoFixable: false, humanInputRequired: true, issues: [],
        }}
      />,
    );

    expect(html).toContain("image-review-card--accepted");
    expect(html).not.toContain("已接受图解");
    expect(html).not.toContain("AI 视觉审核");
    expect(html).not.toContain("接受结果");
    expect(html).not.toContain("修改这张图");
    expect(html).not.toContain("恢复上一版");
    expect(html).not.toContain("查看 AI 审核");
    expect(html).not.toContain("检测到框外变化的区域");
  });

  it("surfaces an accept failure as an alert while keeping the actions usable", () => {
    const html = renderToStaticMarkup(
      <ImageReviewCard {...baseProps} acceptError="当前任务状态不允许接受结果。" />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("当前任务状态不允许接受结果。");
    expect(html).toContain("接受结果");
  });
});
