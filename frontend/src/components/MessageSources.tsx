import { CaretDown, FileText } from "@phosphor-icons/react";
import type { KnowledgeSource } from "../services/generationService";

export function MessageSources({ sources }: { sources: KnowledgeSource[] }) {
  if (sources.length === 0) return null;
  return (
    <aside className="message-sources" aria-label="回答参考来源">
      <strong className="message-sources__title">参考来源 {sources.length}</strong>
      {sources.map((source, index) => (
        <details className="message-source" key={`${source.fileName}-${source.page}-${index}`}>
          <summary className="message-source__summary">
            <FileText aria-hidden="true" weight="duotone" />
            <span className="message-source__file">{source.sourceTitle ?? source.fileName}</span>
            <span className="message-source__page">
              {source.page
                ? `第${source.page}页`
                : source.sourceType === "pubmed"
                  ? `PubMed${source.year ? ` · ${source.year}` : ""}`
                  : source.sourceType === "curated"
                    ? "人工审核知识"
                    : "官方网页"}
            </span>
            <CaretDown className="message-source__caret" aria-hidden="true" />
          </summary>
          {source.section && <p className="message-source__section">{source.section}</p>}
          <p className="message-source__excerpt">{source.content}</p>
          {source.sourceUrl && (
            <a className="message-source__link" href={source.sourceUrl} target="_blank" rel="noreferrer">
              {source.sourceType === "pubmed"
                ? "查看 PubMed"
                : source.sourceType === "curated"
                  ? "查看主要证据"
                  : "查看官网原文"}
            </a>
          )}
        </details>
      ))}
    </aside>
  );
}
