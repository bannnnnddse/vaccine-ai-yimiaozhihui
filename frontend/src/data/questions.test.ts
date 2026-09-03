import { describe, expect, it } from "vitest";
import { emptyKnowledgeTopic, knowledgeTopics } from "./questions";

describe("knowledgeTopics", () => {
  it("按问题一至四映射各自的成品图", () => {
    expect(knowledgeTopics.map((topic) => topic.image)).toEqual([
      "/assets/questions/question-1.png",
      "/assets/questions/question-2.png",
      "/assets/questions/question-3.png",
      "/assets/questions/question-4.png",
    ]);
  });

  it("初始知识状态不预选图片", () => {
    expect(emptyKnowledgeTopic.image).toBe("");
    expect(emptyKnowledgeTopic.question).toBe("");
  });
});
