import { ClipboardText, ClockCounterClockwise } from "@phosphor-icons/react";
import type { DigitalHumanTemplate } from "../config/digitalHumanConfig";
import type { DigitalHumanBubble as BubbleData, DigitalHumanState } from "../hooks/useDigitalHumanInteraction";
import { AdminEntryLink } from "./AdminEntryLink";
import { AvatarGuide } from "./AvatarGuide";
import { DigitalHumanBubble } from "./DigitalHumanBubble";
import { PromptTemplatePanel } from "./PromptTemplatePanel";

interface AssistantContextPanelProps {
  onHistory: () => void;
  state: DigitalHumanState;
  bubble: BubbleData | null;
  panelOpen: boolean;
  panelTitle: string;
  templates: readonly DigitalHumanTemplate[];
  onAvatarActivate: () => void;
  onPanelClose: () => void;
  onTemplateSelect: (template: DigitalHumanTemplate) => void;
}

export function AssistantContextPanel({
  onHistory,
  state,
  bubble,
  panelOpen,
  panelTitle,
  templates,
  onAvatarActivate,
  onPanelClose,
  onTemplateSelect,
}: AssistantContextPanelProps) {
  return (
    <aside className="assistant-context-panel" aria-label="数字人助手信息" data-od-id="assistant-identity-panel">
      <DigitalHumanBubble bubble={bubble} />
      <PromptTemplatePanel
        open={panelOpen}
        title={panelTitle}
        templates={templates}
        onSelect={onTemplateSelect}
        onClose={onPanelClose}
      />
      <div className="assistant-context-panel__portrait">
        <AvatarGuide
          state={state}
          interactive
          panelOpen={panelOpen}
          onActivate={onAvatarActivate}
        />
      </div>
      <div className="assistant-context-panel__utilities">
        <button className="assistant-context-panel__utility-button" data-testid="image-history-entry" type="button" onClick={onHistory} aria-haspopup="dialog">
          <ClockCounterClockwise weight="duotone" aria-hidden="true" />
          <span>历史记录</span>
        </button>
        <span className="assistant-context-panel__admin">
          <ClipboardText weight="duotone" aria-hidden="true" />
          <AdminEntryLink />
        </span>
      </div>
    </aside>
  );
}
