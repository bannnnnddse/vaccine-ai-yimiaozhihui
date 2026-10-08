import { describe, expect, it } from "vitest";
import { isStoredFigureEvidence, parseFigureEvidence } from "./generationService";

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

describe("image evidence boundary", () => {
  it("maps source provenance and preserves evidence through history validation", () => {
    const result = parseFigureEvidence(fixture());
    expect(result.sources[0].page).toBe(2);
    expect(result.medicalReviewRequired).toBe(true);
    expect(isStoredFigureEvidence(JSON.parse(JSON.stringify(result)))).toBe(true);
  });
  it.each(["fake-link", "fake-source", "fake-quote", "missing-step", "duplicate", "medical-approved", "fractional-index"])("rejects %s", (kind) => {
    const value = fixture();
    if (kind === "fake-link") value.sources[0].source_url = "javascript:alert(1)";
    if (kind === "fake-source") value.bindings[0].source_id = "E9";
    if (kind === "fake-quote") value.bindings[0].quote = "原文没有出现这一句话。";
    if (kind === "missing-step") value.bindings.pop();
    if (kind === "duplicate") value.bindings.push(value.bindings[0]);
    if (kind === "medical-approved") Object.assign(value, { medical_review_required: false });
    if (kind === "fractional-index") value.bindings[0].index = .5;
    expect(() => parseFigureEvidence(value)).toThrow();
  });
  it("rejects tampered persisted evidence rather than restoring an unsafe source link", () => {
    const value = parseFigureEvidence(fixture());
    value.sources[0].sourceUrl = "javascript:alert(1)";
    expect(isStoredFigureEvidence(value)).toBe(false);
  });
});
