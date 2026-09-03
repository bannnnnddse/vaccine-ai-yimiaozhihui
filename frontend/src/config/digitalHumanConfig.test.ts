import { describe, expect, it } from "vitest";
import { DIGITAL_HUMAN_CONFIG } from "./digitalHumanConfig";

describe("digital human configuration", () => {
  it("keeps the complete QA and image template sets in one configuration", () => {
    expect(DIGITAL_HUMAN_CONFIG.qaTemplates).toHaveLength(6);
    expect(DIGITAL_HUMAN_CONFIG.imageTemplates).toHaveLength(3);
    expect(DIGITAL_HUMAN_CONFIG.qaTemplates.every((template) => template.prompt.length > template.title.length)).toBe(true);
    expect(DIGITAL_HUMAN_CONFIG.imageTemplates.every((template) => template.prompt.includes("["))).toBe(true);
  });

  it("starts the idle delay only after the configured welcome duration", () => {
    expect(DIGITAL_HUMAN_CONFIG.timing.welcomeDurationMs).toBe(4_500);
    expect(DIGITAL_HUMAN_CONFIG.timing.idleHintDelayMs).toBe(3_000);
  });

  it("shows the template invitation immediately when QA first opens", () => {
    expect(DIGITAL_HUMAN_CONFIG.bubbles.qaWelcome).toBe("不知道怎么问？点击我看看模板吧~");
  });
});
