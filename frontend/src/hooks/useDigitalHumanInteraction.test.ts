import { describe, expect, it } from "vitest";
import { createDigitalHumanModeSessionStore } from "./useDigitalHumanInteraction";

describe("digital human mode sessions", () => {
  it("does not count switching into the target mode as a meaningful interaction", () => {
    const sessions = createDigitalHumanModeSessionStore();
    sessions.enter("chat");
    sessions.markMeaningful("chat");

    expect(sessions.enter("illustration")).toBe("welcome");
    expect(sessions.get("illustration").meaningfulInteraction).toBe(false);
    expect(sessions.enter("illustration")).toBe("idle-wait");
  });

  it("keeps onboarding and idle eligibility independent for QA and Image", () => {
    const sessions = createDigitalHumanModeSessionStore();
    expect(sessions.enter("chat")).toBe("welcome");
    expect(sessions.enter("illustration")).toBe("welcome");

    sessions.markMeaningful("illustration");
    expect(sessions.enter("illustration")).toBe("none");
    expect(sessions.enter("chat")).toBe("idle-wait");
  });

  it("shows an idle hint at most once per mode session", () => {
    const sessions = createDigitalHumanModeSessionStore();
    sessions.enter("chat");
    expect(sessions.enter("chat")).toBe("idle-wait");
    sessions.markIdleHintShown("chat");
    expect(sessions.enter("chat")).toBe("none");
  });
});
