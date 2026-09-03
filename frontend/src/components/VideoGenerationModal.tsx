import { ArrowLeft, Play, Plus, VideoCamera, X } from "@phosphor-icons/react";
import { useState } from "react";

export interface ScienceVideoEpisode {
  id: "virus-adventure" | "vaccine-defense";
  episode: string;
  title: string;
  duration: string;
  description: string;
  poster: string;
  src: string;
}

export const scienceVideoEpisodes: readonly ScienceVideoEpisode[] = [
  {
    id: "virus-adventure",
    episode: "第一集",
    title: "病毒历险记",
    duration: "1 分 57 秒",
    description: "跟随小病毒走进城市，认识传播与防护的第一课。",
    poster: "/assets/science-videos/virus-adventure-episode-1.jpg",
    src: "/assets/science-videos/virus-adventure-episode-1.mp4",
  },
  {
    id: "vaccine-defense",
    episode: "第二集",
    title: "疫苗防御战",
    duration: "1 分 27 秒",
    description: "走进人体防线，看看疫苗如何帮助免疫系统准备应对挑战。",
    poster: "/assets/science-videos/vaccine-defense-episode-2.jpg",
    src: "/assets/science-videos/vaccine-defense-episode-2.mp4",
  },
];

interface VideoGenerationModalProps {
  open: boolean;
  embedded?: boolean;
  onClose: () => void;
}

export function VideoGenerationModal({ open, embedded = false, onClose }: VideoGenerationModalProps) {
  const [selectedEpisode, setSelectedEpisode] = useState<ScienceVideoEpisode | null>(null);
  const [playbackError, setPlaybackError] = useState(false);

  if (!open) return null;

  const chooseEpisode = (episode: ScienceVideoEpisode) => {
    setPlaybackError(false);
    setSelectedEpisode(episode);
  };

  const returnToCollection = () => {
    setPlaybackError(false);
    setSelectedEpisode(null);
  };

  return (
    <div className={`modal-backdrop${embedded ? " video-page" : ""}`} role={embedded ? undefined : "presentation"} onMouseDown={embedded ? undefined : onClose}>
      <section className={`modal-card video-modal${embedded ? " video-modal--embedded" : ""}`} role={embedded ? "region" : "dialog"} aria-modal={embedded ? undefined : true} aria-labelledby="video-title" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="关闭科普短视频"><X /></button>
        {selectedEpisode ? (
          <div className="science-video-player-view">
            <button className="science-video-back" type="button" onClick={returnToCollection}>
              <ArrowLeft weight="bold" aria-hidden="true" /> 返回选集
            </button>
            <div className="science-video-player-view__heading">
              <span className="modal-kicker">{selectedEpisode.episode}</span>
              <h2 id="video-title">{selectedEpisode.title}</h2>
              <p>{selectedEpisode.description}</p>
            </div>
            <video
              className="science-video-player"
              controls
              autoPlay
              playsInline
              preload="metadata"
              poster={selectedEpisode.poster}
              onCanPlay={() => setPlaybackError(false)}
              onError={() => setPlaybackError(true)}
            >
              <source src={selectedEpisode.src} type="video/mp4" />
              你的浏览器暂不支持此视频播放。
            </video>
            {playbackError && <p className="science-video-error" role="alert">视频暂时无法加载，请检查网络后重试。</p>}
          </div>
        ) : (
          <div className="science-video-collection">
            <div className="video-modal__hero">
              <span><VideoCamera weight="regular" /></span>
              <div>
                <h2 id="video-title">用两集动画，看懂病毒与疫苗</h2>
              </div>
            </div>
            <p className="science-video-collection__intro">可选择一集开始观看</p>
            <div className="science-video-grid" aria-label="科普短视频选集">
              {scienceVideoEpisodes.map((episode, index) => (
                <button
                  className={`science-video-card science-video-card--${index + 1}`}
                  data-testid={`science-video-${episode.id}`}
                  key={episode.id}
                  type="button"
                  onClick={() => chooseEpisode(episode)}
                >
                  <img src={episode.poster} alt={`${episode.title}封面`} />
                  <span className="science-video-card__scrim" aria-hidden="true" />
                  <span className="science-video-card__bubble" aria-hidden="true">点击播放</span>
                  <span className="science-video-card__content">
                    <span className="science-video-card__meta">{episode.episode} · {episode.duration}</span>
                    <strong>{episode.title}</strong>
                    <small>{episode.description}</small>
                  </span>
                  <span className="science-video-card__play" aria-hidden="true"><Play weight="fill" /></span>
                </button>
              ))}
              <article className="science-video-coming-soon" aria-label="系列持续更新中">
                <span className="science-video-coming-soon__plus" aria-hidden="true"><Plus weight="regular" /></span>
                <strong>持续更新中</strong>
                <small>更多篇章敬请期待</small>
              </article>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
