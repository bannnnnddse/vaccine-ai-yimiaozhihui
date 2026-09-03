import { ArrowRight, Graph } from "@phosphor-icons/react";

interface FeatureEntryCardsProps {
  onInteractive: () => void;
  onVideo: () => void;
  onGraph: () => void;
}

export function FeatureEntryCards({ onInteractive, onVideo, onGraph }: FeatureEntryCardsProps) {
  return (
    <section className="feature-entries" aria-label="更多疫苗科普功能">
      <button className="feature-card feature-card--graph" type="button" onClick={onGraph}>
        <span className="feature-card__icon"><Graph size={27} weight="duotone" aria-hidden="true" /></span>
        <span className="feature-card__copy"><strong>知识图谱</strong></span>
        <span className="feature-card__action">查看图谱<ArrowRight weight="bold" /></span>
      </button>
      <button className="feature-card feature-card--interactive" type="button" onClick={onInteractive}>
        <span className="feature-card__icon">
          <img src="/assets/boxicons--monitor-filled.svg" alt="" aria-hidden="true" />
        </span>
        <span className="feature-card__copy"><strong>交互页面</strong></span>
        <span className="feature-card__action">立即体验<ArrowRight weight="bold" /></span>
      </button>
      <button className="feature-card feature-card--video" type="button" onClick={onVideo}>
        <span className="feature-card__icon">
          <img src="/assets/movie.svg" alt="" aria-hidden="true" />
        </span>
        <span className="feature-card__copy"><strong>科普短视频</strong></span>
        <span className="feature-card__action">开始创作<ArrowRight weight="bold" /></span>
      </button>
    </section>
  );
}
