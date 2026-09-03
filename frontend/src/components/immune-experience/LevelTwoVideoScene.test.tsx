import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LevelTwoVideoScene } from "./LevelTwoVideoScene";

describe("LevelTwoVideoScene", () => {
  it("renders the interactive presentation scene and not a video", () => {
    const markup = renderToStaticMarkup(<LevelTwoVideoScene onEnded={() => undefined} />);

    expect(markup).toContain("immune-level-two-video-scene");
    expect(markup).toContain("immune-capture");
    expect(markup).toContain("挣扎！");
    expect(markup).not.toContain("<video");
  });
});
