import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ChatInput, getComposerTextareaMetrics, mergeVoiceText, shouldSubmitComposerKey } from "./ChatInput";

describe("ChatInput", () => {
  const props = { value: "水痘发病机制", disabled: false, mode: "illustration" as const, onChange: vi.fn(), onSubmit: vi.fn(), onModeChange: vi.fn() };

  it("uses a stop control while an image is generating", () => {
    const markup = renderToStaticMarkup(<ChatInput {...props} isImageGenerating isCancellingImage={false} onCancelImage={vi.fn()} />);
    expect(markup).toContain('data-state="stop"');
    expect(markup).toContain("chat-input__submit--stop");
    expect(markup).toContain('aria-label="停止生成图片"');
    expect(markup).toContain("chat-input__stop-icon");
    expect(markup).toContain("disabled=\"\"");
  });

  it("keeps the stop control disabled while cancellation is pending", () => {
    const markup = renderToStaticMarkup(<ChatInput {...props} isImageGenerating isCancellingImage onCancelImage={vi.fn()} />);
    expect(markup).toContain('data-state="cancelling"');
    expect(markup).toContain('disabled=""');
  });

  it("renders an accessible voice control in chat mode", () => {
    const markup = renderToStaticMarkup(<ChatInput {...props} mode="chat" />);
    expect(markup).toContain("chat-input__voice");
    expect(markup).toContain('aria-label="开始语音输入"');
  });

  it("merges a transcript snapshot onto the fixed text captured before listening", () => {
    expect(mergeVoiceText("九价HPV疫苗", "适合什么年龄的人接种")).toBe("九价HPV疫苗适合什么年龄的人接种");
    expect(mergeVoiceText("儿童接种疫苗", " 有哪些注意事项")).toBe("儿童接种疫苗有哪些注意事项");
  });

  it("renders a one-row textarea that can grow with wrapped content", () => {
    const markup = renderToStaticMarkup(<ChatInput {...props} mode="chat" />);
    expect(markup).toContain("<textarea");
    expect(markup).toContain('rows="1"');
  });

  it("caps the visible composer at four lines and then enables scrolling", () => {
    expect(getComposerTextareaMetrics(72, 21, 20)).toEqual({ height: 72, scrollable: false });
    expect(getComposerTextareaMetrics(180, 21, 20)).toEqual({ height: 104, scrollable: true });
  });

  it("keeps Enter to send while reserving Shift+Enter for a newline", () => {
    expect(shouldSubmitComposerKey("Enter", false, false)).toBe(true);
    expect(shouldSubmitComposerKey("Enter", true, false)).toBe(false);
    expect(shouldSubmitComposerKey("Enter", false, true)).toBe(false);
  });
});
