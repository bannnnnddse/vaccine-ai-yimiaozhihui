import { describe, expect, it } from "vitest";
import { createTypingFrames } from "./typewriter";

describe("createTypingFrames", () => {
  it("每一帧只增加一个完整字符", () => {
    expect(createTypingFrames("疫苗🩺")).toEqual(["疫", "疫苗", "疫苗🩺"]);
  });
});
