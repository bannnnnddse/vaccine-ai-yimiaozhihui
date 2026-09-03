import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ChatMessage, type ImageResultChatMessage, type ImageStatusChatMessage, type TextChatMessage } from "./ChatMessage";

describe("ChatMessage text formatting", () => {
  it("renders bold Markdown in an assistant answer", () => {
    const message: TextChatMessage = {
      id: "answer-1", role: "assistant", kind: "text",
      content: "接种前请先了解 **总体原则：** 并如实告知健康状况。",
    };

    const markup = renderToStaticMarkup(<ChatMessage message={message} />);

    expect(markup).toContain("<strong>总体原则：</strong>");
    expect(markup).not.toContain("**总体原则：**");
  });

  it("keeps user Markdown as plain text and does not render answer HTML", () => {
    const userMessage: TextChatMessage = {
      id: "user-1", role: "user", kind: "text", content: "**请不要加粗**",
    };
    const assistantMessage: TextChatMessage = {
      id: "answer-2", role: "assistant", kind: "text", content: "安全回答\n\n<script>alert('x')</script>",
    };

    const userMarkup = renderToStaticMarkup(<ChatMessage message={userMessage} />);
    const assistantMarkup = renderToStaticMarkup(<ChatMessage message={assistantMessage} />);

    expect(userMarkup).toContain("**请不要加粗**");
    expect(userMarkup).not.toContain("<strong>");
    expect(assistantMarkup).not.toContain("<script>");
    expect(assistantMarkup).toContain("安全回答");
  });
});

describe("ChatMessage image states", () => {
  it("renders a quiet process trace for an active image job", () => {
    const message: ImageStatusChatMessage = {
      id: "status-1", role: "assistant", kind: "image-status", prompt: "水痘发病机制",
      jobId: "job-1", requestToken: "request-1", stage: "generating",
      traceEvents: [{ id: "trace-1", stage: "generation", title: "正在生成第一版图像", detail: "已提交至 Wan 图像生成模型。", status: "running", createdAt: "2026-08-13T10:00:00Z" }],
    };
    const markup = renderToStaticMarkup(<ChatMessage message={message} />);

    expect(markup).toContain("image-process-trace");
    expect(markup).toContain("chat-message--image-process");
    expect(markup).not.toContain("chat-message--image-generation");
    expect(markup).toContain("正在生成第一版图像");
    expect(markup).toContain("已提交至 Wan 图像生成模型");
    expect(markup).not.toContain("particle-grid__particle");
    expect(markup).not.toContain("取消");
    expect(markup).not.toContain("重试");
  });

  it.each([
    ["failed", "图片生成失败，请重新输入主题"],
    ["cancelled", "已取消本次图片生成"],
  ] as const)("renders %s as a compact terminal message", (stage, error) => {
    const message: ImageStatusChatMessage = {
      id: `status-${stage}`, role: "assistant", kind: "image-status", prompt: "水痘发病机制",
      jobId: "job-1", requestToken: "request-1", stage, error,
      traceEvents: [],
    };
    const markup = renderToStaticMarkup(<ChatMessage message={message} />);
    expect(markup).toContain("image-status--compact");
    expect(markup).toContain(error);
    expect(markup).not.toContain("image-generation-frame");
    expect(markup).not.toContain("image-status__marker");
    expect(markup).not.toContain("button");
  });

  it("keeps the generated image in the same generation frame", () => {
    const message: ImageResultChatMessage = {
      id: "result-1", role: "assistant", kind: "image-result", prompt: "水痘发病机制",
      jobId: "job-1", requestToken: "request-1", imageUrl: "/api/v1/generated-images/job-1.png",
      imageId: "job-1-v0", stage: "completed", autoRevisionCount: 0,
      traceId: "trace-1", traceEvents: [{ id: "trace-1-1", stage: "completed", title: "图解已准备完成", status: "completed", createdAt: "2026-08-13T10:00:00Z" }],
    };
    const markup = renderToStaticMarkup(<ChatMessage message={message} />);
    expect(markup).toContain("image-review-card");
    expect(markup).toContain('src="/api/v1/generated-images/job-1.png"');
    expect(markup).toContain('alt="AI 生成的科学图解"');
    expect(markup).toContain("思考过程");
    expect(markup).toContain('aria-expanded="false"');
  });
});
