import { knowledgeTopics, type KnowledgeTopic } from "../data/questions";

interface SuggestedQuestionsProps {
  selectedId: string;
  disabled: boolean;
  onSelect: (topic: KnowledgeTopic) => void;
}

export function SuggestedQuestions({ selectedId, disabled, onSelect }: SuggestedQuestionsProps) {
  return (
    <section className="suggestions" aria-labelledby="suggestions-title">
      <div className="suggestions__heading">
        <strong id="suggestions-title">可以从这些问题开始</strong>
      </div>
      <div className="suggestions__grid">
        {knowledgeTopics.map((topic) => (
          <button
            type="button"
            className={selectedId === topic.id ? "suggestion-chip is-selected" : "suggestion-chip"}
            disabled={disabled}
            onClick={() => onSelect(topic)}
            key={topic.id}
          >
            {topic.question}
          </button>
        ))}
      </div>
    </section>
  );
}
