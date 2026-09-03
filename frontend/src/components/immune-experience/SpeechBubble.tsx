export interface SpeechBubbleProps {
  children: string;
  align?: "left" | "center" | "right";
  tone?: "info" | "warning" | "success";
}

export function SpeechBubble({ children, align = "center", tone = "info" }: SpeechBubbleProps) {
  return (
    <div
      className={`immune-level-three-speech is-${align} is-${tone}`}
      role="status"
      aria-live="polite"
    >
      {children.split("\n").map((line) => <span key={line}>{line}</span>)}
    </div>
  );
}
