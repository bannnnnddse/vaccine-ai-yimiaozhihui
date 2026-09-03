import { advanceSimulation, countStates, createComparisonSimulation, createSeededRandom, createSimulation, DEFAULT_CONTROL_PARAMETERS, DEFAULT_PARAMETERS } from "./simulationModel";
import { describe, expect, it } from "vitest";

describe("疫苗防线模型", () => {
  it("0% 接种时没有有效保护者或未有效保护者", () => {
    const state = createSimulation({ ...DEFAULT_PARAMETERS, population: 100, vaccinatedPercent: 0, efficacyPercent: 0, sickPercent: 0 }, () => .5);
    expect(countStates(state.particles)).toMatchObject({ vaccinated: 0, unprotected: 0, healthy: 100 });
  });

  it("100% 接种且 0% 有效性时接种者为未有效保护者，并且仍可感染", () => {
    const params = { ...DEFAULT_PARAMETERS, population: 2, vaccinatedPercent: 100, efficacyPercent: 0, sickPercent: 0, infectionPercent: 100 };
    const initial = createSimulation(params, () => .5);
    expect(countStates(initial.particles)).toMatchObject({ vaccinated: 0, unprotected: 2 });
    initial.particles[0] = { ...initial.particles[0], state: "sick", sickFor: 0, x: 40, y: 30 };
    initial.particles[1] = { ...initial.particles[1], state: "unprotected", x: 41, y: 30 };
    const next = advanceSimulation(initial, params, .01, () => 0);
    expect(next.particles[1].state).toBe("sick");
  });

  it("100% 接种且 100% 有效性时不产生未有效保护者", () => {
    const state = createSimulation({ ...DEFAULT_PARAMETERS, population: 100, vaccinatedPercent: 100, efficacyPercent: 100, sickPercent: 0 }, () => .5);
    expect(countStates(state.particles)).toMatchObject({ vaccinated: 100, unprotected: 0 });
  });

  it("50/50 和 80/90 都按接种率和有效性生成状态", () => {
    const half = createSimulation({ ...DEFAULT_PARAMETERS, population: 100, vaccinatedPercent: 50, efficacyPercent: 50, sickPercent: 0 }, () => .5);
    expect(countStates(half.particles)).toMatchObject({ vaccinated: 0, unprotected: 50, healthy: 50 });
    const strong = createSimulation({ ...DEFAULT_PARAMETERS, population: 100, vaccinatedPercent: 80, efficacyPercent: 90, sickPercent: 0 }, () => .1);
    expect(countStates(strong.particles)).toMatchObject({ vaccinated: 80, unprotected: 0, healthy: 20 });
  });

  it("绿色和紫色会感染，红色在病程结束后转为康复或死亡", () => {
    const params = { ...DEFAULT_PARAMETERS, population: 1, vaccinatedPercent: 0, sickPercent: 100, deathPercent: 100 };
    const initial = createSimulation(params, () => .5);
    expect(advanceSimulation(initial, params, 6, () => 0).particles[0].state).toBe("dead");
  });

  it("同一随机种子下两组拥有相同的位置、速度、社交距离与初始感染起点", () => {
    const shared = { ...DEFAULT_PARAMETERS, population: 40, sickPercent: 10, distancingPercent: 30 };
    const comparison = createComparisonSimulation({ ...DEFAULT_CONTROL_PARAMETERS, ...shared, vaccinatedPercent: 0, efficacyPercent: 0 }, shared, createSeededRandom(42));
    expect(comparison.control.particles.map(({ x, y, vx, vy, distancing }) => ({ x, y, vx, vy, distancing })))
      .toEqual(comparison.experiment.particles.map(({ x, y, vx, vy, distancing }) => ({ x, y, vx, vy, distancing })));
    expect(comparison.control.particles.filter((particle) => particle.state === "sick").map((particle) => [particle.x, particle.y]))
      .toEqual(comparison.experiment.particles.filter((particle) => particle.state === "sick").map((particle) => [particle.x, particle.y]));
  });

  it("累计感染和峰值随传播更新，模拟时长限制为三十秒", () => {
    const params = { ...DEFAULT_PARAMETERS, population: 2, vaccinatedPercent: 0, sickPercent: 50, infectionPercent: 100 };
    const initial = createSimulation(params, () => .5);
    initial.particles[0] = { ...initial.particles[0], state: "sick", sickFor: 0, x: 40, y: 30 };
    initial.particles[1] = { ...initial.particles[1], state: "healthy", x: 41, y: 30 };
    const infected = advanceSimulation(initial, params, .01, () => 0);
    expect(infected.cumulativeInfected).toBe(2);
    expect(infected.peakInfected).toBe(2);
    expect(advanceSimulation(infected, params, 100, () => .5)).toMatchObject({ elapsed: 30, completed: true });
  });
});
