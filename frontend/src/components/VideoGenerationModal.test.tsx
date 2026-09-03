import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { scienceVideoEpisodes, VideoGenerationModal } from "./VideoGenerationModal";

const source = readFileSync(new URL("./VideoGenerationModal.tsx", import.meta.url), "utf8");

describe("VideoGenerationModal", () => {
  it("publishes the two supplied local episodes with their posters and native playback metadata", () => {
    expect(scienceVideoEpisodes).toEqual([
      expect.objectContaining({
        title: "病毒历险记",
        duration: "1 分 57 秒",
        poster: "/assets/science-videos/virus-adventure-episode-1.jpg",
        src: "/assets/science-videos/virus-adventure-episode-1.mp4",
      }),
      expect.objectContaining({
        title: "疫苗防御战",
        duration: "1 分 27 秒",
        poster: "/assets/science-videos/vaccine-defense-episode-2.jpg",
        src: "/assets/science-videos/vaccine-defense-episode-2.mp4",
      }),
    ]);

    const markup = renderToStaticMarkup(<VideoGenerationModal open embedded onClose={() => undefined} />);
    expect(markup).toContain("病毒历险记");
    expect(markup).toContain("疫苗防御战");
    expect(markup).toContain("持续更新中");
    expect(markup).toContain("更多篇章敬请期待");
    expect(markup).toContain("可选择一集开始观看");
    expect(markup).not.toContain("疫苗科普放映室");
    expect(markup).toContain('data-testid="science-video-virus-adventure"');
    expect(markup).toContain('data-testid="science-video-vaccine-defense"');
  });

  it("does not render while closed", () => {
    expect(renderToStaticMarkup(<VideoGenerationModal open={false} onClose={() => undefined} />)).toBe("");
  });

  it("keeps native playback, back navigation, and error handling in the component contract", () => {
    expect(source).toContain("<video");
    expect(source).toContain("controls");
    expect(source).toContain("autoPlay");
    expect(source).toContain("playsInline");
    expect(source).toContain("onError={() => setPlaybackError(true)}");
    expect(source).toContain("返回选集");
    expect(source).toContain("视频暂时无法加载");
  });
});
