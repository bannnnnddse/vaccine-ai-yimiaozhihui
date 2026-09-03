import { ClockCounterClockwise, DownloadSimple, Images, X } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";
import type { ImageHistoryEntry } from "../services/imageHistory";
import { ImageProcessTrace } from "./ImageProcessTrace";

interface ImageHistoryModalProps {
  entries: ImageHistoryEntry[];
  open: boolean;
  onClose: () => void;
}

const originCopy = {
  initial: "首次生成",
  auto: "AI 自动修订",
  human: "用户局部编辑",
} as const;

export function ImageHistoryModal({ entries, open, onClose }: ImageHistoryModalProps) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus?.();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocus.current?.focus?.();
    };
  }, [onClose, open]);

  if (!open) return null;
  return <div className="image-history-backdrop" onMouseDown={(event) => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="image-history-modal" data-testid="image-history-modal" role="dialog" aria-modal="true" aria-labelledby="image-history-title">
      <header className="image-history-modal__header">
        <div className="image-history-modal__title">
          <span aria-hidden="true"><ClockCounterClockwise weight="duotone" /></span>
          <div><small>24 小时生成档案</small><h2 id="image-history-title">历史记录</h2></div>
        </div>
        <button ref={closeButton} className="image-history-modal__close" type="button" onClick={onClose} aria-label="关闭历史记录">
          <X weight="bold" aria-hidden="true" />
        </button>
      </header>
      <p className="image-history-modal__notice">记录将在各自生成完成 24 小时后自动移除。这里的内容仅供查看和保存，不会重新进入当前对话。</p>
      <div className="image-history-modal__content">
        {entries.length === 0 ? <div className="image-history-empty">
          <Images weight="duotone" aria-hidden="true" />
          <strong>还没有生成记录</strong>
          <p>完成的科学图解会暂存在这里，刷新页面也可以继续查看。</p>
        </div> : <ol className="image-history-list">
          {entries.map((entry) => <li className="image-history-card" key={entry.id}>
            <figure className="image-history-card__media">
              <img src={entry.imageUrl} alt={`历史科学图解：${entry.prompt}`} />
            </figure>
            <div className="image-history-card__details">
              <div className="image-history-card__meta">
                <span>{entry.revisionOrigin ? originCopy[entry.revisionOrigin] : "生成结果"}</span>
                <time dateTime={new Date(entry.createdAt).toISOString()}>{formatHistoryTime(entry.createdAt)}</time>
              </div>
              <h3>{entry.prompt}</h3>
              <ImageProcessTrace events={entry.traceEvents} completed />
              <a className="image-history-card__download" href={entry.imageUrl} download={`${safeFilename(entry.imageId)}.png`}>
                <DownloadSimple weight="bold" aria-hidden="true" />保存图片
              </a>
            </div>
          </li>)}
        </ol>}
      </div>
    </section>
  </div>;
}

function formatHistoryTime(timestamp: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(timestamp));
}

function safeFilename(imageId: string): string {
  return imageId.replace(/[^a-zA-Z0-9_-]/g, "-") || "science-illustration";
}
