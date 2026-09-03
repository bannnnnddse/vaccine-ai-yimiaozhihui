import type { DigitalHumanBubble as BubbleData } from "../hooks/useDigitalHumanInteraction";

interface DigitalHumanBubbleProps {
  bubble: BubbleData | null;
}

export function DigitalHumanBubble({ bubble }: DigitalHumanBubbleProps) {
  if (!bubble) return null;
  return (
    <div
      className={`digital-human-bubble digital-human-bubble--${bubble.kind}`}
      role={bubble.kind === "error" ? "alert" : "status"}
      aria-live={bubble.kind === "error" ? "assertive" : "polite"}
      data-testid="digital-human-bubble"
    >
      {bubble.message}
    </div>
  );
}
