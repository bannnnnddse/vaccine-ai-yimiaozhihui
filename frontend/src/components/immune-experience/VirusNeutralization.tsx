import type { CSSProperties } from "react";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import type { LevelThreePhase, LevelThreePosition } from "./levelThreeState";

export interface VirusNeutralizationProps {
  phase: LevelThreePhase;
}

export interface VirusNeutralizationParticle {
  id: number;
  virusIndex: number;
  source: LevelThreePosition;
  drift: LevelThreePosition;
  bindingAngle: number;
  bindingRadius: number;
  rotation: number;
  delay: number;
  size: number;
}

interface NeutralizationVirus {
  position: LevelThreePosition;
  entryX: number;
  rotation: number;
  delay: number;
  duration: number;
}

const PLASMA_SOURCES: LevelThreePosition[] = [
  { x: 16, y: 72 },
  { x: 34, y: 58 },
  { x: 50, y: 80 },
  { x: 66, y: 58 },
  { x: 84, y: 72 },
];

const VIRUSES: NeutralizationVirus[] = [
  { position: { x: 34, y: 43 }, entryX: -7, rotation: -18, delay: 0, duration: 8.4 },
  { position: { x: 58, y: 35 }, entryX: 8, rotation: 21, delay: 0.26, duration: 9.1 },
  { position: { x: 45, y: 62 }, entryX: -11, rotation: -9, delay: 0.54, duration: 8.8 },
  { position: { x: 69, y: 57 }, entryX: 5, rotation: 27, delay: 0.82, duration: 9.5 },
];

export function createVirusNeutralizationParticles(): VirusNeutralizationParticle[] {
  return Array.from({ length: 60 }, (_, id) => ({
    id,
    virusIndex: id % VIRUSES.length,
    source: PLASMA_SOURCES[id % PLASMA_SOURCES.length],
    drift: {
      x: 7 + ((id * 37) % 87),
      y: 9 + ((id * 53) % 77),
    },
    bindingAngle: (id * 137.5) % 360,
    bindingRadius: 48 + (id % 5) * 7,
    rotation: (id * 47) % 360 - 180,
    delay: (id % 15) * 0.035,
    size: 18 + (id % 5) * 3,
  }));
}

/**
 * 最终 9 个抗体的可调位置。
 * virusIndex: 0-3，对应四个病毒；x/y: 相对病毒中心的像素偏移（右/下为正）；rotation: 抗体旋转角度。
 */
export const VIRUS_BINDING_ANTIBODY_POSITIONS = [
  { virusIndex: 0, x: -65, y: -21, rotation:90 },
  { virusIndex: 0, x: 40, y: -36, rotation: 260 },
  { virusIndex: 0, x: 8, y: 25, rotation: -20 },
  { virusIndex: 1, x: -60, y: -41, rotation: 110 },
  { virusIndex: 1, x: 38, y: 0, rotation: -60 },
  { virusIndex: 2, x: -60, y: -0, rotation: 60 },
  { virusIndex: 2, x: 30, y: 9, rotation: -50 },
  { virusIndex: 3, x: -60, y: -35, rotation: 100 },
  { virusIndex: 3, x:20, y: 20, rotation: -30},
] as const;

const FOCUS_DRIFT_POSITIONS: LevelThreePosition[] = [
  { x: 18, y: 25 },
  { x: 47, y: 18 },
  { x: 81, y: 28 },
  { x: 22, y: 52 },
  { x: 77, y: 46 },
  { x: 30, y: 76 },
  { x: 58, y: 79 },
  { x: 46, y: 44 },
  { x: 82, y: 72 },
];
export function createVirusBindingParticles(): VirusNeutralizationParticle[] {
  return VIRUS_BINDING_ANTIBODY_POSITIONS.map((position, id) => ({
    id,
    virusIndex: position.virusIndex,
    source: PLASMA_SOURCES[id % PLASMA_SOURCES.length],
    drift: FOCUS_DRIFT_POSITIONS[id],
    bindingAngle: Math.atan2(position.y, position.x) * 180 / Math.PI,
    bindingRadius: Math.hypot(position.x, position.y),
    rotation: position.rotation,
    delay: (id % 3) * .08,
    size: 23 + (id % 3) * 2,
  }));
}

function virusStyle(virus: NeutralizationVirus): CSSProperties {
  return {
    left: `${virus.position.x}%`,
    top: `${virus.position.y}%`,
    "--virus-entry-x": `${virus.entryX}vw`,
    "--virus-settle-x": `${virus.entryX * .12}vw`,
    "--virus-rotation": `${virus.rotation}deg`,
    "--virus-delay": `${virus.delay}s`,
    "--virus-float-duration": `${virus.duration}s`,
  } as CSSProperties;
}

function antibodyStyle(
  particle: VirusNeutralizationParticle,
  virus: NeutralizationVirus,
): CSSProperties {
  const angle = particle.bindingAngle * Math.PI / 180;
  return {
    "--antibody-source-x": `${particle.source.x - virus.position.x}vw`,
    "--antibody-source-y": `${particle.source.y - virus.position.y}vh`,
    "--antibody-drift-x": `${particle.drift.x - virus.position.x}vw`,
    "--antibody-drift-y": `${particle.drift.y - virus.position.y}vh`,
    "--antibody-bind-x": `${Math.cos(angle) * particle.bindingRadius}px`,
    "--antibody-bind-y": `${Math.sin(angle) * particle.bindingRadius}px`,
    "--antibody-overshoot-x": `${Math.cos(angle) * particle.bindingRadius * 1.18}px`,
    "--antibody-overshoot-y": `${Math.sin(angle) * particle.bindingRadius * 1.18}px`,
    "--antibody-rebound-x": `${Math.cos(angle) * particle.bindingRadius * .94}px`,
    "--antibody-rebound-y": `${Math.sin(angle) * particle.bindingRadius * .94}px`,
    "--antibody-bind-rotate": `${particle.rotation}deg`,
    "--antibody-bind-delay": `${particle.delay}s`,
    "--antibody-size": `${particle.size}px`,
    "--antibody-drift-duration": `${8 + (particle.id % 7) * .7}s`,
    "--antibody-wiggle-x": `${(particle.id % 3 - 1) * 11}px`,
    "--antibody-wiggle-y": `${((particle.id * 2) % 5 - 2) * 6}px`,
  } as CSSProperties;
}

export function VirusNeutralization({ phase }: VirusNeutralizationProps) {
  const ambientParticles = createVirusNeutralizationParticles();
  const bindingParticles = createVirusBindingParticles();
  const showViruses = phase === "virus-entry" || phase === "antibody-binding" || phase === "neutralized";
  const showAmbientParticles = phase === "antibody" || phase === "antibody-drift" || phase === "virus-entry";
  const showBindingParticles = phase === "virus-entry" || phase === "antibody-binding" || phase === "neutralized";
  const ambientParticleState = phase === "antibody"
    ? "is-secreting"
    : phase === "virus-entry"
      ? "is-withdrawing"
      : "is-drifting";
  const bindingParticleState = phase === "virus-entry"
    ? "is-emerging"
    : phase === "antibody-binding"
      ? "is-binding"
      : "is-bound";

  return (
    <div className={`immune-virus-neutralization is-${phase}`}>
      {VIRUSES.map((virus, virusIndex) => (
        <div
          className={`immune-virus-neutralization__cluster${phase === "neutralized" ? " is-neutralized" : ""}`}
          key={virusIndex}
          style={virusStyle(virus)}
        >
          {showViruses && (
            <img
              className={`immune-virus-neutralization__virus${phase === "virus-entry" ? " is-entering" : ""}`}
              data-neutralization-virus={virusIndex}
              src={level3Assets.virus}
              alt="被抗体识别的病毒"
              draggable={false}
            />
          )}
          {showAmbientParticles && ambientParticles.filter((particle) => particle.virusIndex === virusIndex).map((particle) => (
            <img
              className={`immune-virus-neutralization__antibody ${ambientParticleState}`}
              data-antibody-particle
              data-withdrawing-antibody={phase === "virus-entry" ? particle.id : undefined}
              key={`ambient-${particle.id}`}
              src={level3Assets.redAntibody}
              alt=""
              aria-hidden="true"
              style={antibodyStyle(particle, virus)}
            />
          ))}
          {showBindingParticles && bindingParticles.filter((particle) => particle.virusIndex === virusIndex).map((particle) => (
            <img
              className={`immune-virus-neutralization__antibody ${bindingParticleState}`}
              data-binding-antibody={particle.id}
              data-bound-virus={phase === "neutralized" ? virusIndex : undefined}
              key={`binding-${particle.id}`}
              src={level3Assets.redAntibody}
              alt=""
              aria-hidden="true"
              style={antibodyStyle(particle, virus)}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
