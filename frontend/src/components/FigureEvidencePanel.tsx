import type { FigureBinding, FigureEvidence } from "../services/generationService";

function SourceQuote({ evidence, binding }: {
  evidence: FigureEvidence;
  binding: FigureBinding;
}) {
  const source = evidence.sources.find((item) => item.sourceId === binding.sourceId);
  if (!source) return <p>绑定来源暂不可用，请重新查看任务记录。</p>;
  const location = [source.section, source.page ? `第 ${source.page} 页` : null]
    .filter(Boolean).join(" · ");
  return (
    <div className="figure-evidence__source">
      {source.sourceUrl
        ? <a href={source.sourceUrl} target="_blank" rel="noopener noreferrer">{source.title}</a>
        : <strong>{source.title}</strong>}
      {location && <p>{location}</p>}
      <blockquote>{binding.quote}</blockquote>
    </div>
  );
}

function BoundStatements({ evidence, target, texts }: {
  evidence: FigureEvidence;
  target: FigureBinding["target"];
  texts: string[];
}) {
  return (
    <ol>
      {texts.map((statement, index) => (
        <li key={index}>
          <p>{statement}</p>
          {evidence.bindings
            .filter((binding) => binding.target === target && binding.index === index)
            .map((binding, i) => <SourceQuote key={i} evidence={evidence} binding={binding} />)}
        </li>
      ))}
    </ol>
  );
}

export function FigureEvidencePanel({ evidence }: { evidence?: FigureEvidence }) {
  if (!evidence) {
    return <p className="figure-evidence__notice">此图片没有来源绑定记录，医学内容需人工复核。</p>;
  }
  return (
    <div className="figure-evidence">
      <p className="figure-evidence__notice">科学表述已绑定来源；医学内容仍需人工复核。</p>
      <details>
        <summary>查看科学表述与依据</summary>
        <BoundStatements evidence={evidence} target="claim" texts={evidence.claims} />
        <details>
          <summary>查看因果步骤依据</summary>
          <BoundStatements evidence={evidence} target="step" texts={evidence.steps} />
        </details>
      </details>
    </div>
  );
}
