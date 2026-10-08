import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { parseFigureEvidence } from "../services/generationService";
import { FigureEvidencePanel } from "./FigureEvidencePanel";
import { ImageReviewCard } from "./ImageReviewCard";

export function fixture() {
  const text = "疫苗抗原可触发适应性免疫反应并形成免疫记忆。";
  return { contract_version: "image_evidence_v1", index_version: "index-v1", status: "sources_bound", medical_review_required: true,
    assessment_method: "exact_quote_and_model_support", content_signature: "a".repeat(64),
    claims: [text], steps: [text], sources: [{ source_id: "E1", chunk_id: "chunk-1", document_id: "doc-1",
      file_name: "免疫科普.pdf", title: "免疫科普", page: 2, section: "免疫记忆",
      source_url: "https://example.org/source", source_hash: "hash", content: text }],
    bindings: [{ target: "claim", index: 0, source_id: "E1", quote: text },
      { target: "step", index: 0, source_id: "E1", quote: text }],
  };
}

it("displays traceable quotations without claiming medical approval", () => {
  const html = renderToStaticMarkup(<FigureEvidencePanel evidence={parseFigureEvidence(fixture())} />);
  expect(html).toContain("医学内容仍需人工复核");
  expect(html).toContain("https://example.org/source");
  expect(html).toContain("第 2 页");
  expect(html).toContain("<blockquote>");
  expect(html).not.toContain("医学审核通过");
});
it("keeps source bindings visible after user accepts the illustration", () => {
  const html = renderToStaticMarkup(<ImageReviewCard evidence={parseFigureEvidence(fixture())}
    accepted imageUrl="/api/v1/generated-images/test.png" imageId="id" stage="completed"
    autoRevisionCount={0} onAccept={() => {}} onEdit={() => {}} />);
  expect(html).toContain("查看科学表述与依据");
});
it("does not imply source verification for legacy images", () => {
  expect(renderToStaticMarkup(<FigureEvidencePanel />)).toContain("没有来源绑定记录");
});
