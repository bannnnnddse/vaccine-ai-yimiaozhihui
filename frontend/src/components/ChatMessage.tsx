import ReactMarkdown from "react-markdown";
import type { ImageJobStage, KnowledgeSource } from "../services/generationService";
import { ImageReviewCard } from "./ImageReviewCard";
import { ImageProcessTrace } from "./ImageProcessTrace";
import { MessageSources } from "./MessageSources";

interface ChatMessageBase { id: string; role: "user" | "assistant"; }
export type MessageKind = "text" | "image-status" | "image-result";
export interface TextChatMessage extends ChatMessageBase { kind: "text"; content: string; isTyping?: boolean; sources?: KnowledgeSource[]; }
export type ImageMessageStage = ImageJobStage | "submitting" | "cancelling";
export interface ImageStatusChatMessage extends ChatMessageBase { role: "assistant"; kind: "image-status"; prompt: string; jobId: string | null; requestToken: string; stage: ImageMessageStage; error?: string | null; traceId?: string; traceEvents: import("../services/generationService").ImageProcessEvent[]; isRevealingTrace?: boolean; }
export interface ImageResultChatMessage extends ChatMessageBase { role: "assistant"; kind: "image-result"; prompt: string; jobId: string; requestToken: string; imageUrl: string; imageId: string; stage: ImageJobStage; candidateImageUrl?: string; previousImageUrl?: string; previousImageId?: string; criticResult?: import("../services/generationService").VisualCriticResult; guardResult?: import("../services/generationService").EditScopeGuardResult; autoRevisionCount: number; revisionOrigin?: import("../services/generationService").RevisionOrigin; previousRevisionOrigin?: import("../services/generationService").RevisionOrigin; accepted?: boolean; historical?: boolean; acceptError?: string; traceId: string; traceEvents: import("../services/generationService").ImageProcessEvent[]; }
export type ChatMessageData = TextChatMessage | ImageStatusChatMessage | ImageResultChatMessage;
interface ChatMessageProps { message: ChatMessageData; onImageError?: (messageId: string) => void; onAcceptImage?: (message: ImageResultChatMessage) => void; onRestorePreviousImage?: (message: ImageResultChatMessage) => void; onEditImage?: (message: ImageResultChatMessage, bbox: import("../services/generationService").NormalizedBBox, request: string) => void; onImageTraceRevealComplete?: (messageId: string) => void; onImageInteraction?: () => void; }

const stageCaptions: Record<ImageMessageStage, string> = {
  submitting: "正在创建图解任务…",
  queued: "任务排队中…", rewriting_prompt: "提示词优化中…", generating: "图片生成中…",
  critic_review_1: "AI 首次审核中…", auto_revising: "AI 自动修订中…", guard_check: "编辑范围保护检查中…",
  critic_review_2: "自动修订结果审核中…", awaiting_human_feedback: "等待你的修改建议",
  editing_with_bbox: "区域编辑中…", critic_review_final: "修改结果审核中…",
  cancelling: "正在取消…",
  completed: "图解生成完成",
  failed: "图解生成失败",
  cancelled: "已取消本次图解生成",
};
export function ChatMessage({ message, onImageError, onAcceptImage, onRestorePreviousImage, onEditImage, onImageTraceRevealComplete, onImageInteraction }: ChatMessageProps) {
  if (message.kind === "image-status") {
    const traceEvents = message.traceEvents ?? [];
    if (!["awaiting_human_feedback", "completed", "failed", "cancelled"].includes(message.stage)) {
      return (
        <article className="chat-message chat-message--assistant chat-message--image-process">
          <span className="chat-message__avatar" aria-hidden="true"><img src="/assets/chat-assistant-avatar.png" alt="" /></span>
          <div className="chat-message__content">
            <ImageProcessTrace events={traceEvents} live onRevealComplete={() => onImageTraceRevealComplete?.(message.id)} />
            {traceEvents.length === 0 && <p className="image-process-fallback">{message.error || stageCaptions[message.stage]}</p>}
          </div>
        </article>
      );
    }
    return (
      <article className="chat-message chat-message--assistant chat-message--image-status">
        <span className="chat-message__avatar" aria-hidden="true"><img src="/assets/chat-assistant-avatar.png" alt="" /></span>
        <div className={"chat-message__content image-status image-status--compact image-status--" + message.stage}>
          <ImageProcessTrace events={traceEvents} live={message.isRevealingTrace} onRevealComplete={() => onImageTraceRevealComplete?.(message.id)} />
          <div className="image-status__copy"><strong>{message.error || stageCaptions[message.stage]}</strong></div>
        </div>
      </article>
    );
  }
  if (message.kind === "image-result") {
    const traceEvents = message.traceEvents ?? [];
    return (
      <article className="chat-message chat-message--assistant chat-message--image-generation">
        <span className="chat-message__avatar" aria-hidden="true"><img src="/assets/chat-assistant-avatar.png" alt="" /></span>
        <div className="chat-message__content">
          <ImageProcessTrace events={traceEvents} completed />
          <ImageReviewCard {...message} onAccept={() => onAcceptImage?.(message)} onRestorePrevious={() => onRestorePreviousImage?.(message)} onEdit={(bbox, request) => onEditImage?.(message, bbox, request)} onImageError={() => onImageError?.(message.id)} onInteraction={onImageInteraction} />
        </div>
      </article>
    );
  }
  return (
    <article className={"chat-message chat-message--" + message.role + " chat-message--text"}>
      {message.role === "assistant" && <span className="chat-message__avatar" aria-hidden="true"><img src="/assets/chat-assistant-avatar.png" alt="" /></span>}
      <div className="chat-message__content">
        {message.role === "assistant"
          ? <div className="chat-message__markdown"><ReactMarkdown skipHtml>{message.content}</ReactMarkdown></div>
          : message.content}
        {message.isTyping && <span className="typing-cursor" aria-hidden="true" />}
        {message.role === "assistant" && !message.isTyping && message.sources && message.sources.length > 0
          && <MessageSources sources={message.sources} />}
      </div>
    </article>
  );
}
