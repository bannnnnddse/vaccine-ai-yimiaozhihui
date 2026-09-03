import { useEffect, useRef } from "react";
import type { DigitalHumanTemplate } from "../config/digitalHumanConfig";

interface PromptTemplatePanelProps {
  open: boolean;
  title: string;
  templates: readonly DigitalHumanTemplate[];
  onSelect: (template: DigitalHumanTemplate) => void;
  onClose: () => void;
}

export function PromptTemplatePanel({ open, title, templates, onSelect, onClose }: PromptTemplatePanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (panelRef.current?.contains(target) || target.closest("[data-digital-human-trigger]")) return;
      onClose();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  if (!open) return null;
  return (
    <div
      ref={panelRef}
      className="prompt-template-panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="prompt-template-panel-title"
      data-testid="prompt-template-panel"
    >
      <div className="prompt-template-panel__scroll">
        <strong id="prompt-template-panel-title">{title}</strong>
        <div className="prompt-template-panel__grid">
          {templates.map((template) => (
            <button key={template.id} type="button" onClick={() => onSelect(template)}>
              <span>{template.title}</span>
              <small>{template.prompt}</small>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
