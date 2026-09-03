import type { CSSProperties } from "react";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import type { LevelThreePosition } from "./levelThreeState";

export interface AntibodyAnimationProps {
  origin?: LevelThreePosition;
  origins?: LevelThreePosition[];
  asset?: string;
}

const ANTIBODY_COUNT = 40;

export function AntibodyAnimation({ origin, origins, asset = level3Assets.antibody }: AntibodyAnimationProps) {
  const sources = origins ?? (origin ? [origin] : []);
  if (sources.length === 0) return null;
  return (
    <div className="immune-level-three-antibodies" aria-hidden="true">
      {Array.from({ length: ANTIBODY_COUNT }, (_, index) => {
        const source = sources[index % sources.length];
        const angle = (index / ANTIBODY_COUNT) * Math.PI * 2;
        const distance = 70 + ((index * 37) % 210);
        const style = {
          left: `${source.x}%`,
          top: `${source.y}%`,
          "--antibody-x": `${Math.cos(angle) * distance}px`,
          "--antibody-y": `${Math.sin(angle) * distance * 0.72}px`,
          "--antibody-rotate": `${(index * 53) % 260 - 130}deg`,
          "--antibody-delay": `${(index % 10) * 0.12}s`,
          "--antibody-duration": `${5 + (index % 4) * 0.7}s`,
          "--antibody-size": `${20 + (index % 5) * 5}px`,
        } as CSSProperties;
        return <img key={index} data-antibody-particle src={asset} alt="" style={style} />;
      })}
    </div>
  );
}
