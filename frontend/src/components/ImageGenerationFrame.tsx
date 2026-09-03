import { useState, type CSSProperties } from "react";

export const PARTICLE_COLUMNS = 9;
export const PARTICLE_ROWS = 6;

export interface ImageParticle {
  row: number;
  column: number;
  phase: number;
  restScale: number;
  restOpacity: number;
}

export function createImageParticles(): ImageParticle[] {
  const centerX = (PARTICLE_COLUMNS - 1) / 2;
  const centerY = (PARTICLE_ROWS - 1) / 2;
  const maximumDistance = Math.hypot(centerX, centerY);

  return Array.from({ length: PARTICLE_ROWS * PARTICLE_COLUMNS }, (_, index) => {
    const row = Math.floor(index / PARTICLE_COLUMNS);
    const column = index % PARTICLE_COLUMNS;
    const distance = Math.hypot(column - centerX, row - centerY);
    const normalizedDistance = distance / maximumDistance;
    return {
      row,
      column,
      phase: distance * 0.11 + (row + column) * 0.012,
      restScale: 1 - normalizedDistance * 0.34,
      restOpacity: 0.88 - normalizedDistance * 0.5,
    };
  });
}

const imageParticles = createImageParticles();

type ParticleStyle = CSSProperties & {
  "--particle-delay": string;
  "--particle-rest-scale": number;
  "--particle-rest-opacity": number;
};

interface ImageGenerationFrameProps {
  title: string;
  imageUrl?: string;
  alt: string;
  onImageError?: () => void;
}

export function ImageGenerationFrame({
  title,
  imageUrl,
  alt,
  onImageError,
}: ImageGenerationFrameProps) {
  const [isReady, setIsReady] = useState(false);

  const handleLoad = () => setIsReady(true);

  return (
    <figure
      className={`image-generation-frame${isReady ? " is-ready" : ""}`}
      aria-busy={!isReady}
    >
      <div className="image-generation-placeholder">
        <div className="generation-content">
          <div className="generation-text">
            <strong className="generation-title">{title}</strong>
          </div>
          <div className="particle-grid" aria-hidden="true">
            {imageParticles.map((particle) => (
              <i
                className="particle-grid__particle"
                data-row={particle.row}
                data-column={particle.column}
                key={`${particle.row}-${particle.column}`}
                style={{
                  "--particle-delay": `${-particle.phase}s`,
                  "--particle-rest-scale": particle.restScale,
                  "--particle-rest-opacity": particle.restOpacity,
                } as ParticleStyle}
              />
            ))}
          </div>
        </div>
      </div>
      {imageUrl && (
        <img
          className="image-generation-frame__image"
          src={imageUrl}
          alt={alt}
          onLoad={handleLoad}
          onError={onImageError}
        />
      )}
    </figure>
  );
}
