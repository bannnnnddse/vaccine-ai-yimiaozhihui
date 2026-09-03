export type HealthState = "healthy" | "vaccinated" | "unprotected" | "sick" | "recovered" | "dead";

export interface SimulationParameters {
  population: number;
  vaccinatedPercent: number;
  efficacyPercent: number;
  sickPercent: number;
  infectionPercent: number;
  distancingPercent: number;
  deathPercent: number;
}

export interface Particle {
  state: HealthState;
  x: number;
  y: number;
  vx: number;
  vy: number;
  distancing: boolean;
  immune: boolean;
  sickFor: number;
}

export interface SimulationStats {
  cumulativeInfected: number;
  peakInfected: number;
  currentInfected: number;
  recovered: number;
  dead: number;
}

export interface SimulationState {
  particles: Particle[];
  elapsed: number;
  history: Record<HealthState, number>[];
  cumulativeInfected: number;
  peakInfected: number;
  completed: boolean;
}

export interface ComparisonSimulationState {
  control: SimulationState;
  experiment: SimulationState;
}

interface InitialParticle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  vaccineRank: number;
  efficacyRoll: number;
  infectionRank: number;
  distancingRank: number;
}

export const DEFAULT_PARAMETERS: SimulationParameters = {
  population: 125, vaccinatedPercent: 80, efficacyPercent: 90, sickPercent: 1,
  infectionPercent: 100, distancingPercent: 0, deathPercent: 3,
};

export const DEFAULT_CONTROL_PARAMETERS: SimulationParameters = {
  ...DEFAULT_PARAMETERS, vaccinatedPercent: 0, efficacyPercent: 0,
};

export const STATES: HealthState[] = ["healthy", "vaccinated", "unprotected", "sick", "recovered", "dead"];
export const STATE_COLORS: Record<HealthState, string> = {
  healthy: "#9acb6c", vaccinated: "#60bce8", unprotected: "#8d76c9", sick: "#e8574f", recovered: "#f0a64a", dead: "#252b35",
};

const radius = 0.8;
const speed = 0.2;
const width = 100;
const height = 100 * 2 / 3;
const sicknessDuration = 6;
const duration = 30;

export function createSeededRandom(seed: number) {
  let value = seed >>> 0;
  return () => {
    value += 0x6D2B79F5;
    let result = value;
    result = Math.imul(result ^ result >>> 15, result | 1);
    result ^= result + Math.imul(result ^ result >>> 7, result | 61);
    return ((result ^ result >>> 14) >>> 0) / 4294967296;
  };
}

export function countStates(particles: Particle[]): Record<HealthState, number> {
  const counts = Object.fromEntries(STATES.map((state) => [state, 0])) as Record<HealthState, number>;
  for (const particle of particles) counts[particle.state] += 1;
  return counts;
}

function createInitialParticles(params: SimulationParameters, random: () => number): InitialParticle[] {
  return Array.from({ length: params.population }, () => {
    const angle = random() * Math.PI * 2;
    return {
      x: radius + random() * (width - radius * 2),
      y: radius + random() * (height - radius * 2),
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      vaccineRank: random(), efficacyRoll: random(), infectionRank: random(), distancingRank: random(),
    };
  });
}

function canBeInfected(ball: Particle) {
  return ball.state === "healthy" || ball.state === "unprotected";
}

function stateFromInitial(params: SimulationParameters, initial: InitialParticle[], sharedInfectionIndexes?: number[]): SimulationState {
  const vaccinatedCount = Math.floor(params.population * params.vaccinatedPercent / 100);
  const vaccinatedIndexes = new Set(initial
    .map((particle, index) => ({ index, rank: particle.vaccineRank }))
    .sort((a, b) => a.rank - b.rank)
    .slice(0, vaccinatedCount)
    .map(({ index }) => index));
  const particles = initial.map((base, index): Particle => {
    const isVaccinated = vaccinatedIndexes.has(index);
    const immune = isVaccinated && base.efficacyRoll < params.efficacyPercent / 100;
    return {
      state: immune ? "vaccinated" : isVaccinated ? "unprotected" : "healthy",
      x: base.x, y: base.y, vx: base.vx, vy: base.vy,
      distancing: base.distancingRank < params.distancingPercent / 100,
      immune, sickFor: sicknessDuration,
    };
  });
  const requestedInitialInfected = Math.floor(params.population * params.sickPercent / 100);
  const infectionIndexes = sharedInfectionIndexes ?? particles
    .map((particle, index) => ({ index, rank: initial[index].infectionRank, particle }))
    .filter(({ particle }) => canBeInfected(particle))
    .sort((a, b) => a.rank - b.rank)
    .slice(0, requestedInitialInfected)
    .map(({ index }) => index);
  for (const index of infectionIndexes) {
    const particle = particles[index];
    if (!particle || !canBeInfected(particle)) continue;
    particle.state = "sick";
    particle.sickFor = 0;
  }
  const counts = countStates(particles);
  return {
    particles, elapsed: 0, history: [counts], cumulativeInfected: counts.sick,
    peakInfected: counts.sick, completed: false,
  };
}

export function createSimulation(params: SimulationParameters, random = Math.random): SimulationState {
  return stateFromInitial(params, createInitialParticles(params, random));
}

/** Both arms derive from the exact same initial locations and movement vectors. */
export function createComparisonSimulation(control: SimulationParameters, experiment: SimulationParameters, random = Math.random): ComparisonSimulationState {
  const initial = createInitialParticles(experiment, random);
  const controlWithoutCases = stateFromInitial({ ...control, sickPercent: 0 }, initial);
  const experimentWithoutCases = stateFromInitial({ ...experiment, sickPercent: 0 }, initial);
  const caseCount = Math.floor(Math.min(control.sickPercent, experiment.sickPercent) * experiment.population / 100);
  const sharedInfectionIndexes = initial
    .map((particle, index) => ({ index, rank: particle.infectionRank }))
    .filter(({ index }) => canBeInfected(controlWithoutCases.particles[index]) && canBeInfected(experimentWithoutCases.particles[index]))
    .sort((a, b) => a.rank - b.rank)
    .slice(0, caseCount)
    .map(({ index }) => index);
  return {
    control: stateFromInitial(control, initial, sharedInfectionIndexes),
    experiment: stateFromInitial(experiment, initial, sharedInfectionIndexes),
  };
}

function reflect(ball: Particle, axis: "x" | "y") { ball[axis === "x" ? "vx" : "vy"] *= -1; }

export function getSimulationStats(state: SimulationState): SimulationStats {
  const counts = countStates(state.particles);
  return {
    cumulativeInfected: state.cumulativeInfected, peakInfected: state.peakInfected,
    currentInfected: counts.sick, recovered: counts.recovered, dead: counts.dead,
  };
}

export function advanceSimulation(previous: SimulationState, params: SimulationParameters, seconds: number, random = Math.random): SimulationState {
  if (previous.completed) return previous;
  const particles = previous.particles.map((particle) => ({ ...particle }));
  const infectionRate = params.infectionPercent / 100;
  const deathRate = params.deathPercent / 100;
  let newlyInfected = 0;
  for (let first = 0; first < particles.length; first += 1) {
    for (let second = first + 1; second < particles.length; second += 1) {
      const a = particles[first]; const b = particles[second];
      if (a.state === "dead" || b.state === "dead") continue;
      const dx = a.x - b.x; const dy = a.y - b.y;
      const distance = Math.hypot(dx, dy);
      if (distance > radius * 2) continue;
      const nx = distance === 0 ? 1 : dx / distance; const ny = distance === 0 ? 0 : dy / distance;
      const overlap = radius * 2 - distance + 0.001;
      if (!a.distancing) { a.x += nx * overlap / 2; a.y += ny * overlap / 2; }
      if (!b.distancing) { b.x -= nx * overlap / 2; b.y -= ny * overlap / 2; }
      const dot = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny;
      if (!a.distancing && !b.distancing) { a.vx -= dot * nx; a.vy -= dot * ny; b.vx += dot * nx; b.vy += dot * ny; }
      if ((a.state === "sick" && canBeInfected(b)) || (b.state === "sick" && canBeInfected(a))) {
        if (random() < infectionRate) {
          if (canBeInfected(a)) { a.state = "sick"; a.sickFor = 0; newlyInfected += 1; }
          if (canBeInfected(b)) { b.state = "sick"; b.sickFor = 0; newlyInfected += 1; }
        }
      }
    }
  }
  for (const ball of particles) {
    if (ball.state === "sick") {
      ball.sickFor += seconds;
      if (ball.sickFor >= sicknessDuration) ball.state = random() < deathRate ? "dead" : "recovered";
    }
    if (ball.distancing || ball.state === "dead") continue;
    ball.x += ball.vx * seconds * 60; ball.y += ball.vy * seconds * 60;
    if (ball.x <= radius || ball.x >= width - radius) { ball.x = Math.max(radius, Math.min(width - radius, ball.x)); reflect(ball, "x"); }
    if (ball.y <= radius || ball.y >= height - radius) { ball.y = Math.max(radius, Math.min(height - radius, ball.y)); reflect(ball, "y"); }
  }
  const elapsed = Math.min(duration, previous.elapsed + seconds);
  const counts = countStates(particles);
  return {
    particles, elapsed, history: [...previous.history, counts],
    cumulativeInfected: previous.cumulativeInfected + newlyInfected,
    peakInfected: Math.max(previous.peakInfected, counts.sick), completed: elapsed >= duration,
  };
}
