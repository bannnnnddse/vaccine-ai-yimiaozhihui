import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ImageHistoryEntry } from "../services/imageHistory";
import { ImageHistoryModal } from "./ImageHistoryModal";

const entry: ImageHistoryEntry = {
  id: "image-history-job-1-v0",
  imageId: "job-1-v0",
  imageUrl: "/api/v1/generated-images/job-1-v0.png",
  jobId: "job-1",
  prompt: "疫苗如何建立免疫记忆",
  autoRevisionCount: 0,
  revisionOrigin: "initial",
  traceId: "trace-1",
  traceEvents: [{ id: "trace-1-1", stage: "completed", title: "图解已准备完成", detail: "最终图片已生成。", status: "completed", createdAt: "2026-08-14T10:00:00Z" }],
  createdAt: Date.parse("2026-08-14T10:00:00Z"),
  expiresAt: Date.parse("2026-08-15T10:00:00Z"),
};

describe("ImageHistoryModal", () => {
  it("renders a read-only record with trace and a direct PNG download", () => {
    const markup = renderToStaticMarkup(<ImageHistoryModal entries={[entry]} open onClose={() => undefined} />);
    expect(markup).toContain('role="dialog"');
    expect(markup).toContain("疫苗如何建立免疫记忆");
    expect(markup).toContain("思考过程");
    expect(markup).toContain('download="job-1-v0.png"');
    expect(markup).not.toContain("修改这张图");
    expect(markup).not.toContain("接受结果");
  });

  it("renders a calm empty state", () => {
    const markup = renderToStaticMarkup(<ImageHistoryModal entries={[]} open onClose={() => undefined} />);
    expect(markup).toContain("还没有生成记录");
  });
});
