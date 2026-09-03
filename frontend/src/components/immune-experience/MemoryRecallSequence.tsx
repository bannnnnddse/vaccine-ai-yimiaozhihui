import type { CSSProperties } from "react";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import type { LevelThreePhase } from "./levelThreeState";

type MemoryRecallPhase = Extract<
  LevelThreePhase,
  | "memory-recall"
  | "memory-awakening"
  | "memory-antibody-storm"
  | "iris-focus"
  | "iris-hold"
  | "iris-close"
  | "blackout"
>;

export interface MemoryRecallSequenceProps {
  phase: MemoryRecallPhase;
}

export interface MemoryRecallAntibody {
  id: number;
  x: number;
  y: number;
  rotation: number;
  delay: number;
  duration: number;
  size: number;
}

interface RecallVirusTrack {
  startY: number;
  endX: number;
  endY: number;
  delay: number;
  rotation: number;
  duration: number;
}

const RECALL_VIRUS_TRACKS: RecallVirusTrack[] = [
  { startY: 18, endX: 10, endY: 30, delay: 0, rotation: 34, duration: 1.9 },
  { startY: 51, endX: 2, endY: 49, delay: 0.16, rotation: -27, duration: 2.15 },
  { startY: 82, endX: 14, endY: 70, delay: 0.31, rotation: 41, duration: 2.35 },
];

const ANTIBODY_PHASES: MemoryRecallPhase[] = [
  "memory-antibody-storm",
  "iris-focus",
  "iris-hold",
  "iris-close",
];

function halton(index: number, base: number) {
  let value = 0;
  let fraction = 1 / base;
  let current = index;

  while (current > 0) {
    value += fraction * (current % base);
    current = Math.floor(current / base);
    fraction /= base;
  }

  return value;
}

export function createMemoryRecallAntibodies(): MemoryRecallAntibody[] {
  return Array.from({ length: 240 }, (_, id) => ({
      id,
      x: 6 + halton(id + 1, 2) * 88,
      y: 6 + halton(id + 1, 3) * 88,
      rotation: (id * 47) % 360 - 180,
      delay: (id % 30) * 0.025,
      duration: 2.8 + (id % 9) * 0.18,
      size: 12 + (id % 5) * 2,
    }));
}

function virusStyle(track: RecallVirusTrack): CSSProperties {
  return {
    "--recall-virus-start-y": `${track.startY}vh`,
    "--recall-virus-end-x": `${track.endX}px`,
    "--recall-virus-end-y": `${track.endY}vh`,
    "--recall-virus-rotation": `${track.rotation}deg`,
    "--recall-virus-delay": `${track.delay}s`,
    "--recall-virus-duration": `${track.duration}s`,
  } as CSSProperties;
}

function antibodyStyle(particle: MemoryRecallAntibody): CSSProperties {
  return {
    width: `calc(${particle.size}px * var(--memory-antibody-size-scale))`,
    "--recall-antibody-x": `${particle.x - 78}vw`,
    "--recall-antibody-y": `${particle.y - 50}vh`,
    "--recall-antibody-rotation": `${particle.rotation}deg`,
    "--recall-antibody-delay": `${particle.delay}s`,
    "--recall-antibody-duration": `${particle.duration}s`,
  } as CSSProperties;
}

export function MemoryRecallSequence({ phase }: MemoryRecallSequenceProps) {
  const showViruses = phase === "memory-recall" || phase === "memory-awakening";
  const showSleepingCell = phase === "memory-recall" || phase === "memory-awakening";
  const showAngryCell = phase !== "memory-recall" && phase !== "blackout";
  const showAntibodies = ANTIBODY_PHASES.includes(phase);
  const antibodies = showAntibodies ? createMemoryRecallAntibodies() : [];

  return (
    <div className={`immune-memory-recall is-${phase}`} aria-hidden="true">
      {showViruses && RECALL_VIRUS_TRACKS.map((track, index) => (
        <img
          className="immune-memory-recall__virus"
          data-recall-virus={index + 1}
          src={level3Assets.virusParticle}
          alt=""
          draggable={false}
          key={index}
          style={virusStyle(track)}
        />
      ))}

      <div className="immune-memory-recall__cell">
        {showSleepingCell && (
          <img
            className="immune-memory-recall__cell-layer is-sleeping"
            src={level3Assets.sleepingMemoryBCell}
            alt=""
            draggable={false}
          />
        )}
        {showAngryCell && (
          <img
            className="immune-memory-recall__cell-layer is-angry"
            src={level3Assets.angryMemoryBCell}
            alt=""
            draggable={false}
          />
        )}
      </div>

      {antibodies.map((particle) => (
        <img
          className="immune-memory-recall__antibody"
          data-recall-antibody={particle.id}
          aria-hidden="true"
          src={level3Assets.redAntibody}
          alt=""
          draggable={false}
          key={particle.id}
          style={antibodyStyle(particle)}
        />
      ))}
    </div>
  );
}
