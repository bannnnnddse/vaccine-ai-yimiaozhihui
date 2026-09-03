import { useCallback, useEffect, useRef, useState, type Ref } from "react";
import type { KnowledgeTopic } from "../data/questions";
import { ChatInput, type ChatMode } from "./ChatInput";
import { ChatMessage, type ChatMessageData, type ImageResultChatMessage } from "./ChatMessage";
import type { NormalizedBBox } from "../services/generationService";
import { SuggestedQuestions } from "./SuggestedQuestions";
import { TextType } from "./TextType";

interface ChatPanelProps {
  messages: ChatMessageData[];
  input: string;
  isAnswering: boolean;
  isTypingAnswer: boolean;
  chatProgress: string | null;
  selectedQuestionId: string;
  mode?: ChatMode;
  onInputChange: (value: string) => void;
  onSubmit: (question: string) => void;
  onSelectQuestion: (topic: KnowledgeTopic) => void;
  onModeChange?: (mode: ChatMode) => void;
  onCancelImage?: () => void;
  onImageLoadError?: (messageId: string) => void;
  onAcceptImage?: (message: ImageResultChatMessage) => void;
  onRestorePreviousImage?: (message: ImageResultChatMessage) => void;
  onEditImage?: (message: ImageResultChatMessage, bbox: NormalizedBBox, request: string) => void;
  onImageTraceRevealComplete?: (messageId: string) => void;
  inputRef?: Ref<HTMLTextAreaElement>;
  onMeaningfulInteraction?: () => void;
}

export function ChatPanel(props: ChatPanelProps) {
  const messageList = useRef<HTMLDivElement>(null);
  const [welcomeFirstLineComplete, setWelcomeFirstLineComplete] = useState(false);
  const [illustrationFirstLineComplete, setIllustrationFirstLineComplete] = useState(false);
  const handleWelcomeFirstLineComplete = useCallback(() => setWelcomeFirstLineComplete(true), []);
  const handleIllustrationFirstLineComplete = useCallback(
    () => setIllustrationFirstLineComplete(true),
    [],
  );
  const mode = props.mode ?? "chat";
  const activeImageMessage = [...props.messages].reverse().find((message) => (
    (message.kind === "image-status" || message.kind === "image-result")
      && !["completed", "awaiting_human_feedback", "failed", "cancelled"].includes(message.stage)
  ));
  const isImageGenerating = mode === "illustration" && Boolean(activeImageMessage);
  const isCancellingImage = activeImageMessage?.kind === "image-status" && activeImageMessage.stage === "cancelling";

  useEffect(() => {
    const element = messageList.current;
    if (element) element.scrollTo({
      top: element.scrollHeight,
      behavior: props.isTypingAnswer ? "auto" : "smooth",
    });
  }, [props.messages, props.isAnswering, props.isTypingAnswer]);

  return (
    <section className={`chat-panel chat-panel--${mode}`} aria-label={mode === "chat" ? "AI 疫苗问答" : "AI 疫苗图解"}>
      <div className="message-list" ref={messageList} aria-live="polite">
        {mode === "chat" && props.messages.length === 0 && (
          <div className="chat-empty-state">
            <div className="chat-empty-state__title" aria-label="你关心的疫苗问题，都可以从这里开始">
              <TextType
                text="你关心的疫苗问题，"
                typingSpeed={70}
                showCursor={!welcomeFirstLineComplete}
                className="chat-empty-state__title-first"
                onComplete={handleWelcomeFirstLineComplete}
              />
              {welcomeFirstLineComplete && (
                <TextType text="都可以从这里开始" typingSpeed={70} className="chat-empty-state__title-second" />
              )}
            </div>
          </div>
        )}
        {mode === "illustration" && props.messages.length === 0 && (
          <div className="illustration-empty-state">
            <div className="illustration-empty-state__title" aria-label="从图解开始，看懂疫苗疑惑">
              <TextType
                text="从图解开始，"
                typingSpeed={70}
                showCursor={!illustrationFirstLineComplete}
                className="illustration-empty-state__title-first"
                onComplete={handleIllustrationFirstLineComplete}
              />
              {illustrationFirstLineComplete && (
                <TextType
                  text="看懂疫苗疑惑"
                  typingSpeed={70}
                  className="illustration-empty-state__title-second"
                />
              )}
            </div>
          </div>
        )}
        {props.messages.map((message) => (
          <ChatMessage
            message={message}
            key={message.id}
            onImageError={props.onImageLoadError}
            onAcceptImage={props.onAcceptImage}
            onRestorePreviousImage={props.onRestorePreviousImage}
            onEditImage={props.onEditImage}
            onImageTraceRevealComplete={props.onImageTraceRevealComplete}
            onImageInteraction={props.onMeaningfulInteraction}
          />
        ))}
        {mode === "chat" && props.isAnswering && !props.isTypingAnswer && props.chatProgress && (
          <div className="thinking-row"><span className="chat-message__avatar" aria-hidden="true"><img src="/assets/chat-assistant-avatar.png" alt="" /></span><span className="thinking-bubble">{props.chatProgress}<i><b /><b /><b /></i></span></div>
        )}
      </div>
      {mode === "chat" && props.messages.length === 0 && (
        <SuggestedQuestions selectedId={props.selectedQuestionId} disabled={props.isAnswering} onSelect={props.onSelectQuestion} />
      )}
      <ChatInput
        value={props.input}
        disabled={props.isAnswering}
        mode={mode}
        isImageGenerating={isImageGenerating}
        isCancellingImage={isCancellingImage}
        onChange={props.onInputChange}
        onSubmit={props.onSubmit}
        onCancelImage={props.onCancelImage}
        onModeChange={(nextMode) => props.onModeChange?.(nextMode)}
        inputRef={props.inputRef}
        onMeaningfulInteraction={props.onMeaningfulInteraction}
      />
    </section>
  );
}
