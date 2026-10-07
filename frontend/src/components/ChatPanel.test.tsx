import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./ChatPanel";

const baseProps = {
  input: "",
  isAnswering: false,
  isTypingAnswer: false,
  chatProcessSteps: [],
  selectedQuestionId: "",
  mode: "chat" as const,
  onInputChange: vi.fn(),
  onSubmit: vi.fn(),
  onSelectQuestion: vi.fn(),
};

describe("ChatPanel", () => {
  it("shows suggested questions before the conversation starts", () => {
    const markup = renderToStaticMarkup(<ChatPanel {...baseProps} messages={[]} />);

    expect(markup).toContain('aria-label="你关心的疫苗问题，都可以从这里开始"');
    expect(markup).toContain("你关心的疫苗问题，");
    expect(markup).toContain("可以从这些问题开始");
  });

  it("shows the staged illustration welcome title", () => {
    const markup = renderToStaticMarkup(
      <ChatPanel {...baseProps} mode="illustration" messages={[]} />,
    );

    expect(markup).toContain('aria-label="从图解开始，看懂疫苗疑惑"');
    expect(markup).toContain("从图解开始，");
  });

  it("hides suggested questions after a user sends a message", () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        {...baseProps}
        messages={[{ id: "user-1", role: "user", kind: "text", content: "疫苗如何发挥作用？" }]}
      />,
    );

    expect(markup).not.toContain("可以从这些问题开始");
  });

  it("renders accumulated process steps with completed and active states", () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        {...baseProps}
        messages={[]}
        isAnswering
        chatProcessSteps={[
          { id: "rewrite", activeText: "正在分析并改写科学问题…", completedText: "问题理解与改写完成", status: "completed" },
          { id: "retrieval", activeText: "正在检索知识库证据…", completedText: "知识库证据检索完成", status: "active" },
        ]}
      />,
    );

    expect(markup).toContain("thinking-bubble--process");
    expect(markup).toContain("问题理解与改写完成");
    expect(markup).toContain("正在检索知识库证据…");
    expect(markup).toContain("thinking-step__check");
    expect(markup).toContain("thinking-step--completed");
    expect(markup).toContain("thinking-step--active");
    expect(markup).toContain("thinking-step__dots");
  });
});
