import { CaretDown } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { ImageProcessEvent } from "../services/generationService";
import "./ImageProcessTrace.css";

interface ImageProcessTraceProps {
  events: ImageProcessEvent[];
  live?: boolean;
  completed?: boolean;
  onRevealComplete?: () => void;
}

function revealKey(event: ImageProcessEvent): string {
  return `${event.id}:${event.status}:${event.detail ?? ""}`;
}

export function ImageProcessTrace({ events, live = false, completed = false, onRevealComplete }: ImageProcessTraceProps) {
  const [expanded, setExpanded] = useState(!completed);
  const [revealedKeys, setRevealedKeys] = useState<Set<string>>(() => new Set());
  const completedSequenceRef = useRef<string | null>(null);
  const eventKeys = events.map(revealKey);
  const sequence = eventKeys.join("|");

  useEffect(() => {
    if (completed) setExpanded(false);
  }, [completed]);

  useEffect(() => {
    if (!live || !sequence || !eventKeys.every((key) => revealedKeys.has(key))) return;
    if (completedSequenceRef.current === sequence) return;
    completedSequenceRef.current = sequence;
    onRevealComplete?.();
  }, [eventKeys, live, onRevealComplete, revealedKeys, sequence]);

  if (events.length === 0) return null;
  return <section className={`image-process-trace${expanded ? " is-expanded" : ""}`} aria-label="图片生成思考过程">
    {completed && <ImageProcessTraceToggle expanded={expanded} onToggle={() => setExpanded((value) => !value)} />}
    <div className="image-process-trace__viewport" aria-hidden={!expanded}>
      <div className="image-process-trace__events">
        {events.map((event) => <ImageProcessTraceEvent
          event={event}
          reveal={live}
          onRevealComplete={() => setRevealedKeys((current) => {
            const key = revealKey(event);
            return current.has(key) ? current : new Set([...current, key]);
          })}
          key={event.id}
        />)}
      </div>
    </div>
  </section>;
}

export function ImageProcessTraceToggle({ expanded, onToggle }: { expanded: boolean; onToggle: () => void }) {
  return <button className="image-process-trace__toggle" type="button" aria-expanded={expanded} onClick={onToggle}>
    <span>思考过程</span><CaretDown aria-hidden="true" weight="bold" />
  </button>;
}

export function ImageProcessTraceEvent({ event, reveal, onRevealComplete }: {
  event: ImageProcessEvent;
  reveal: boolean;
  onRevealComplete?: () => void;
}) {
  const [detail, setDetail] = useState(reveal ? "" : event.detail ?? "");
  const targetRef = useRef<string | null>(null);
  const indexRef = useRef(0);
  const statusRef = useRef(event.status);

  useEffect(() => {
    const target = event.detail ?? "";
    if (!reveal || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDetail(target);
      targetRef.current = target;
      indexRef.current = target.length;
      statusRef.current = event.status;
      onRevealComplete?.();
      return;
    }
    if (targetRef.current !== null && targetRef.current !== target) {
      const isNewOutcome = statusRef.current === "running" && event.status !== "running";
      targetRef.current = target;
      statusRef.current = event.status;
      if (!isNewOutcome) {
        setDetail(target);
        indexRef.current = target.length;
        return;
      }
      setDetail("");
      indexRef.current = 0;
    }
    if (targetRef.current === null) {
      targetRef.current = target;
      indexRef.current = 0;
      setDetail("");
    }
    statusRef.current = event.status;
    if (!target || indexRef.current >= target.length) {
      onRevealComplete?.();
      return;
    }
    const timer = window.setInterval(() => {
      indexRef.current = Math.min(target.length, indexRef.current + 1);
      setDetail(target.slice(0, indexRef.current));
      if (indexRef.current >= target.length) {
        window.clearInterval(timer);
        onRevealComplete?.();
      }
    }, 16);
    return () => window.clearInterval(timer);
  }, [event.detail, event.id, event.status, onRevealComplete, reveal]);

  return <div className={`image-process-event image-process-event--${event.status}`}>
    <div className="image-process-event__title">
      {event.status === "running" && <i aria-hidden="true" />}{event.title}
    </div>
    {event.detail && <p>{detail}<span className="sr-only">{detail ? "" : event.detail}</span></p>}
  </div>;
}
