import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { ArrowCounterClockwise, ArrowLeft, Pause, Play, SlidersHorizontal, X } from "@phosphor-icons/react";
import { useReducedMotion } from "../immune-experience/useReducedMotion";
import {
  advanceSimulation, countStates, createComparisonSimulation, createSeededRandom,
  getSimulationStats, STATE_COLORS, STATES,
  type ComparisonSimulationState, type HealthState, type SimulationParameters, type SimulationState,
} from "./simulationModel";

const labels: Record<HealthState, string> = {
  healthy: "健康", vaccinated: "有效保护", unprotected: "未有效保护", sick: "感染", recovered: "康复", dead: "死亡",
};

type DiseasePreset = {
  id: string;
  title: string;
  summary: string;
  evidence: string;
  sourceLabel: string;
  sourceUrl: string;
  config: SimulationParameters;
};

const sharedSimulationConfig = {
  population: 125,
  vaccinatedPercent: 80,
  sickPercent: 1,
  infectionPercent: 100,
  distancingPercent: 0,
  deathPercent: 0,
};

// 这些是便于对照观察的固定科普预设，不是临床疫苗效力或真实传播预测值。
export const DISEASE_PRESETS: DiseasePreset[] = [
  {
    id: "covid-19", title: "新型冠状病毒感染",
    summary: "疫苗可降低重症和死亡风险，具体保护会随疫苗产品、接种史和流行变异株而变化。",
    evidence: "WHO：已获认可的疫苗可预防重症和死亡。",
    sourceLabel: "WHO 新型冠状病毒疫苗问答", sourceUrl: "https://www.who.int/news-room/questions-and-answers/item/coronavirus-disease-%28covid-19%29-vaccines",
    config: { ...sharedSimulationConfig, efficacyPercent: 60 },
  },
  {
    id: "pertussis", title: "百日咳",
    summary: "接种含百日咳成分疫苗可提供保护，保护程度和持续时间会随年龄及接种时间而变化。",
    evidence: "CDC：相关疫苗效力点估计约为 80%-85%。",
    sourceLabel: "CDC 百日咳疫苗效力资料", sourceUrl: "https://stacks.cdc.gov/view/cdc/253001/cdc_253001_DS1.pdf",
    config: { ...sharedSimulationConfig, efficacyPercent: 80 },
  },
  {
    id: "influenza-a", title: "甲型流感",
    summary: "季节性流感疫苗的保护效果受当季病毒株与疫苗株匹配程度等因素影响。",
    evidence: "CDC：甲型流感不同亚型的效果可有明显差异。",
    sourceLabel: "CDC 流感疫苗对不同病毒的效果", sourceUrl: "https://www.cdc.gov/flu-vaccines-work/effectiveness/index.html",
    config: { ...sharedSimulationConfig, efficacyPercent: 45 },
  },
  {
    id: "influenza-b", title: "乙型流感",
    summary: "季节性流感疫苗可减轻流感相关疾病负担，但每个流行季的保护表现并不固定。",
    evidence: "CDC 汇总研究中，乙型流感的合并保护估计为 42%。",
    sourceLabel: "CDC 流感疫苗对不同病毒的效果", sourceUrl: "https://www.cdc.gov/flu-vaccines-work/effectiveness/index.html",
    config: { ...sharedSimulationConfig, efficacyPercent: 42 },
  },
  {
    id: "hand-foot-mouth", title: "手足口病（肠道病毒71型相关）",
    summary: "EV-A71 疫苗用于预防 EV-A71 相关手足口病，不覆盖所有引起手足口病的肠道病毒类型。",
    evidence: "国家卫生健康委：该疫苗对 EV-A71 相关手足口病保护率可达 97.3%。",
    sourceLabel: "国家卫生健康委 手足口病防控信息", sourceUrl: "https://www.nhc.gov.cn/xcs/wzbd/201512/c3da33f0b9e64d09937cd939aaab6fb9.shtml",
    config: { ...sharedSimulationConfig, efficacyPercent: 97 },
  },
];

export const SPREAD_INTRO_LINES = [
  "当疫苗接种率变化时，疾病的传播会发生怎样的变化?",
  "我们预设了新冠，百日咳，甲流，乙流，手足口病五种疾病",
  "模拟中，不同颜色的小球代表不同状态的个体。",
  "我们先来预选一种疾病，开始模拟吧！",
] as const;
export const SPREAD_INTRO_ENTER_DURATION_MS = 760;
export const SPREAD_INTRO_EXIT_DURATION_MS = 420;
export const SPREAD_INTRO_HOLD_DURATION_MS = 30_000;

function SpreadIntroNarration({ onComplete, onClose }: { onComplete: () => void; onClose: () => void }) {
  const prefersReducedMotion = useReducedMotion();
  const [lineIndex, setLineIndex] = useState(0);
  const [phase, setPhase] = useState<"entering" | "holding" | "exiting">("entering");
  const completedRef = useRef(false);

  const showNextLine = useCallback(() => {
    if (completedRef.current) return;
    if (lineIndex === SPREAD_INTRO_LINES.length - 1) {
      completedRef.current = true;
      onComplete();
      return;
    }
    setLineIndex((current) => current + 1);
  }, [lineIndex, onComplete]);

  useEffect(() => {
    setPhase(prefersReducedMotion ? "holding" : "entering");
  }, [lineIndex, prefersReducedMotion]);

  useEffect(() => {
    const duration = phase === "entering"
      ? SPREAD_INTRO_ENTER_DURATION_MS
      : phase === "holding"
        ? SPREAD_INTRO_HOLD_DURATION_MS
        : prefersReducedMotion ? 0 : SPREAD_INTRO_EXIT_DURATION_MS;
    const phaseTimer = window.setTimeout(() => {
      if (phase === "entering") setPhase("holding");
      else if (phase === "holding") setPhase("exiting");
      else showNextLine();
    }, duration);
    return () => window.clearTimeout(phaseTimer);
  }, [phase, prefersReducedMotion, showNextLine]);

  const beginExit = useCallback(() => {
    if (phase !== "exiting") setPhase("exiting");
  }, [phase]);

  const stopAndClose = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onClose();
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    beginExit();
  };

  return <section className="spread-intro-page" role="application" tabIndex={0} aria-label="疫苗防线玩法介绍" onClick={beginExit} onKeyDown={handleKeyDown}>
    <button className="spread-intro-page__exit" type="button" onClick={stopAndClose}><ArrowLeft weight="bold" />返回问答</button>
    <div className="spread-intro">
      <p key={lineIndex} role="status" aria-live="polite" data-phase={phase}>{SPREAD_INTRO_LINES[lineIndex]}</p>
    </div>
  </section>;
}

function createControlConfig(experiment: SimulationParameters): SimulationParameters {
  return { ...experiment, vaccinatedPercent: 0, efficacyPercent: 0 };
}

function draw(canvas: HTMLCanvasElement, state: SimulationState) {
  const rect = canvas.getBoundingClientRect(); const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * ratio)); canvas.height = Math.max(1, Math.round(rect.height * ratio));
  const context = canvas.getContext("2d"); if (!context) return;
  context.setTransform(ratio, 0, 0, ratio, 0, 0); context.fillStyle = "#f8fcff"; context.fillRect(0, 0, rect.width, rect.height);
  const sx = rect.width / 100; const sy = rect.height / (100 * 2 / 3);
  for (const particle of state.particles) {
    context.fillStyle = STATE_COLORS[particle.state]; context.beginPath();
    context.arc(particle.x * sx, particle.y * sy, Math.max(3, .8 * sx), 0, Math.PI * 2); context.fill();
  }
}

function drawChart(canvas: HTMLCanvasElement, history: SimulationState["history"], population: number) {
  const rect = canvas.getBoundingClientRect(); const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * ratio)); canvas.height = Math.max(1, Math.round(rect.height * ratio));
  const context = canvas.getContext("2d"); if (!context) return;
  context.setTransform(ratio, 0, 0, ratio, 0, 0); context.fillStyle = "#eef8fd"; context.fillRect(0, 0, rect.width, rect.height);
  const stacked: HealthState[] = ["dead", "recovered", "sick", "unprotected", "healthy", "vaccinated"];
  const totals = history.map(() => 0); const xAt = (index: number) => index / Math.max(1, history.length - 1) * rect.width;
  for (const state of stacked) {
    const lower = [...totals]; history.forEach((point, index) => { totals[index] += point[state]; });
    context.fillStyle = STATE_COLORS[state]; context.beginPath();
    context.moveTo(xAt(0), rect.height - lower[0] / population * rect.height);
    history.forEach((_, index) => context.lineTo(xAt(index), rect.height - totals[index] / population * rect.height));
    for (let index = history.length - 1; index >= 0; index -= 1) context.lineTo(xAt(index), rect.height - lower[index] / population * rect.height);
    context.closePath(); context.fill();
  }
}

function percentageChange(baseline: number, value: number) {
  if (!Number.isFinite(baseline) || !Number.isFinite(value) || baseline <= 0) return null;
  return Math.round((baseline - value) / baseline * 100);
}

function getBarrierCopy(experiment: SimulationParameters, result: ComparisonSimulationState) {
  const control = getSimulationStats(result.control); const active = getSimulationStats(result.experiment);
  const reduced = percentageChange(control.cumulativeInfected, active.cumulativeInfected) ?? 0;
  const estimatedProtection = experiment.vaccinatedPercent * experiment.efficacyPercent / 10000;
  if (estimatedProtection >= .7 && reduced >= 50) return { level: "较强", text: "本轮模拟中，可持续参与传播的易感个体明显减少，实验组的累计感染和感染峰值均低于对照组。" };
  if (reduced >= 10) return { level: "正在形成", text: "本轮模拟中，疫苗干预已经产生影响，但传播仍可发生。可返回选择另一种疾病预设，观察传播链的变化。" };
  return { level: "较弱", text: "本轮模拟中，两组结果差异较小。在当前设定下，疫苗产生的有效保护范围仍较有限。" };
}

function ScenarioPanel({ title, subtitle, runtime, fieldCanvas, chartCanvas }: {
  title: string; subtitle: string; runtime: SimulationState; fieldCanvas: React.RefObject<HTMLCanvasElement | null>; chartCanvas: React.RefObject<HTMLCanvasElement | null>;
}) {
  const counts = countStates(runtime.particles);
  return <section className="spread-scenario" aria-label={`${title}传播模拟`}>
    <header className="spread-scenario__header"><div><h2>{title}</h2><p>{subtitle}</p></div><b>{Math.round(runtime.elapsed)} / 30 秒</b></header>
    <div className="spread-scenario__status" aria-live="polite">{STATES.map((key) => <span key={key}><i aria-hidden="true" style={{ background: STATE_COLORS[key] }} />{labels[key]} <b>{counts[key]}</b></span>)}</div>
    <canvas ref={fieldCanvas} className="spread-scenario__canvas" aria-label={`${title}传播画布`} />
    <div className="spread-scenario__chart-heading"><span>传播趋势</span><span>累计感染 {runtime.cumulativeInfected}</span></div>
    <canvas ref={chartCanvas} className="spread-scenario__chart" aria-label={`${title}传播趋势图`} />
  </section>;
}

export function CoverageAdjustmentDialog({ value, onChange, onClose, onRestart }: {
  value: number; onChange: (value: number) => void; onClose: () => void; onRestart: () => void;
}) {
  return <div className="spread-coverage-backdrop" role="presentation">
    <section className="spread-coverage-dialog" role="dialog" aria-modal="true" aria-labelledby="spread-coverage-title">
      <header><div><span>实验参数</span><h2 id="spread-coverage-title">调整疫苗接种率</h2></div><button className="spread-coverage-dialog__close" type="button" aria-label="关闭接种率调整" onClick={onClose}><X weight="bold" /></button></header>
      <label className="spread-coverage-control" htmlFor="spread-coverage-range"><span>模拟接种覆盖率</span><output htmlFor="spread-coverage-range">{value}%</output></label>
      <input id="spread-coverage-range" type="range" min="0" max="100" step="1" value={value} autoFocus onChange={(event) => onChange(Number(event.currentTarget.value))} />
      <div className="spread-coverage-scale" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div>
      <footer><button type="button" onClick={onRestart}><ArrowCounterClockwise weight="bold" />重新开始</button></footer>
    </section>
  </div>;
}

export function VirusSpreadingSimulation({ onClose }: { onClose: () => void }) {
  const initialPreset = DISEASE_PRESETS[0];
  const [selectedPresetId, setSelectedPresetId] = useState(initialPreset.id);
  const [experimentConfig, setExperimentConfig] = useState(initialPreset.config);
  const [controlConfig, setControlConfig] = useState(() => createControlConfig(initialPreset.config));
  const initialRuntime = createComparisonSimulation(createControlConfig(initialPreset.config), initialPreset.config, createSeededRandom(1));
  const [view, setView] = useState<ComparisonSimulationState>(initialRuntime);
  const [running, setRunning] = useState(false); const [screen, setScreen] = useState<"intro" | "configure" | "simulation">("intro");
  const [coverageDialogOpen, setCoverageDialogOpen] = useState(false);
  const [coverageDraft, setCoverageDraft] = useState(initialPreset.config.vaccinatedPercent);
  const runtime = useRef(initialRuntime); const frame = useRef<number | null>(null); const lastTime = useRef<number | null>(null); const lastFlush = useRef(0);
  const controlRandom = useRef(createSeededRandom(2)); const experimentRandom = useRef(createSeededRandom(3)); const seed = useRef(10);
  const controlField = useRef<HTMLCanvasElement>(null); const experimentField = useRef<HTMLCanvasElement>(null);
  const controlChart = useRef<HTMLCanvasElement>(null); const experimentChart = useRef<HTMLCanvasElement>(null);

  const redraw = () => {
    if (controlField.current) draw(controlField.current, runtime.current.control);
    if (experimentField.current) draw(experimentField.current, runtime.current.experiment);
    if (controlChart.current) drawChart(controlChart.current, runtime.current.control.history, controlConfig.population);
    if (experimentChart.current) drawChart(experimentChart.current, runtime.current.experiment.history, experimentConfig.population);
  };

  useEffect(() => {
    if (screen !== "simulation") return;
    redraw(); const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(redraw);
    [controlField.current, experimentField.current, controlChart.current, experimentChart.current].forEach((canvas) => canvas && observer?.observe(canvas));
    window.addEventListener("resize", redraw);
    return () => { observer?.disconnect(); window.removeEventListener("resize", redraw); };
  // Canvas refs become available only after the simulation screen mounts.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen]);

  useEffect(() => {
    if (!running || screen !== "simulation") return;
    const tick = (now: number) => {
      const seconds = Math.min(.05, Math.max(.001, (now - (lastTime.current ?? now)) / 1000)); lastTime.current = now;
      runtime.current = {
        control: advanceSimulation(runtime.current.control, controlConfig, seconds, controlRandom.current),
        experiment: advanceSimulation(runtime.current.experiment, experimentConfig, seconds, experimentRandom.current),
      };
      redraw();
      if (runtime.current.control.completed && runtime.current.experiment.completed) { setView(runtime.current); setRunning(false); return; }
      if (now - lastFlush.current > 250) { lastFlush.current = now; setView(runtime.current); }
      frame.current = window.requestAnimationFrame(tick);
    };
    frame.current = window.requestAnimationFrame(tick);
    return () => { if (frame.current !== null) window.cancelAnimationFrame(frame.current); frame.current = null; lastTime.current = null; };
  // redraw intentionally reads refs so the animation loop remains stable.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, screen, controlConfig, experimentConfig]);

  useEffect(() => {
    if (!coverageDialogOpen) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setCoverageDialogOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [coverageDialogOpen]);

  const initialize = (start = false, nextControl = controlConfig, nextExperiment = experimentConfig) => {
    const nextSeed = seed.current += 1;
    runtime.current = createComparisonSimulation(nextControl, nextExperiment, createSeededRandom(nextSeed));
    controlRandom.current = createSeededRandom(nextSeed + 1000); experimentRandom.current = createSeededRandom(nextSeed + 2000);
    lastTime.current = null; lastFlush.current = 0; setView(runtime.current); setRunning(start); requestAnimationFrame(redraw);
  };
  const selectedPreset = DISEASE_PRESETS.find((preset) => preset.id === selectedPresetId) ?? initialPreset;
  const selectPreset = (preset: DiseasePreset) => {
    const nextExperiment = { ...preset.config };
    setSelectedPresetId(preset.id); setExperimentConfig(nextExperiment); setControlConfig(createControlConfig(nextExperiment)); setCoverageDraft(nextExperiment.vaccinatedPercent);
  };
  const openCoverageDialog = () => {
    setRunning(false); setCoverageDraft(experimentConfig.vaccinatedPercent); setCoverageDialogOpen(true);
  };
  const restartWithCoverage = () => {
    const nextExperiment = { ...experimentConfig, vaccinatedPercent: coverageDraft };
    const nextControl = createControlConfig(nextExperiment);
    setExperimentConfig(nextExperiment); setControlConfig(nextControl); setCoverageDialogOpen(false);
    initialize(true, nextControl, nextExperiment);
  };
  const configText = (defaultControl = false) => defaultControl ? "未接种对照组" : `${coverageDialogOpen ? coverageDraft : experimentConfig.vaccinatedPercent}% 模拟接种覆盖`;
  const controlStats = getSimulationStats(view.control); const experimentStats = getSimulationStats(view.experiment);
  const complete = view.control.completed && view.experiment.completed;

  if (screen === "intro") return <SpreadIntroNarration onComplete={() => setScreen("configure")} onClose={onClose} />;

  if (screen === "configure") return <section className="spread-config-page" aria-label="疫苗防线参数">
    <button className="spread-config-page__exit" type="button" onClick={onClose}><ArrowLeft weight="bold" />返回问答</button>
    <div className="spread-config"><header><h1>疫苗防线</h1></header>
      <div className="spread-config__controls"><div className="spread-config__section-title"><h2>选择疾病预设</h2></div>
        <div className="spread-disease-grid">{DISEASE_PRESETS.map((preset) => <button key={preset.id} className={`spread-disease-card${preset.id === "hand-foot-mouth" ? " spread-disease-card--hand-foot-mouth" : ""}`} type="button" aria-pressed={selectedPresetId === preset.id} onClick={() => selectPreset(preset)}>
          <strong>{preset.title}</strong><p>{preset.summary}</p>
        </button>)}</div>
        <div className="spread-preset-summary"><strong>当前选择：{selectedPreset.title}</strong><p>对照组沿用相同初始条件，仅将疫苗接种率固定为 0%。</p><a href={selectedPreset.sourceUrl} target="_blank" rel="noreferrer">查看资料依据：{selectedPreset.sourceLabel}</a></div>
      </div>
      <footer><button type="button" onClick={() => { setScreen("simulation"); initialize(true); }}><Play weight="fill" />开始模拟</button></footer>
    </div>
  </section>;

  const barrier = complete ? getBarrierCopy(experimentConfig, view) : null;
  return <section className="spread-run-page" aria-label="疫苗防线运行页面"><header className="spread-run-page__header"><div><span>传播对照实验</span><h1>疫苗防线</h1></div><button type="button" onClick={onClose}>退出体验</button></header>
    <main className="spread-run-page__main"><div className="spread-run-page__scenarios"><ScenarioPanel title="对照组" subtitle={configText(true)} runtime={view.control} fieldCanvas={controlField} chartCanvas={controlChart} /><ScenarioPanel title="实验组" subtitle={`${selectedPreset.title} · ${configText()}`} runtime={view.experiment} fieldCanvas={experimentField} chartCanvas={experimentChart} /></div>
      <div className="spread-run-page__actions"><button className="spread-run-page__secondary-action" type="button" onClick={() => { setRunning(false); setScreen("configure"); }}><SlidersHorizontal weight="bold" />更换疾病预设</button><button type="button" onClick={openCoverageDialog}><SlidersHorizontal weight="bold" />调整接种率</button><button type="button" onClick={() => initialize(false)}><ArrowCounterClockwise weight="bold" />重置</button>{complete ? <button type="button" onClick={() => initialize(true)}><Play weight="fill" />重新开始</button> : <button type="button" onClick={() => setRunning((value) => !value)}>{running ? <><Pause weight="fill" />暂停</> : <><Play weight="fill" />继续</>}</button>}</div>
      {complete && barrier && <section className="spread-result" aria-live="polite"><header><div><span>对照结果</span><h2>免疫屏障：{barrier.level}</h2></div><p>{barrier.text}</p></header><div className="spread-result__metrics"><div><span>累计感染</span><b>{controlStats.cumulativeInfected} → {experimentStats.cumulativeInfected}</b><small>{percentageChange(controlStats.cumulativeInfected, experimentStats.cumulativeInfected) === null ? "无法比较" : `减少 ${controlStats.cumulativeInfected - experimentStats.cumulativeInfected} 人，下降 ${percentageChange(controlStats.cumulativeInfected, experimentStats.cumulativeInfected)}%`}</small></div><div><span>感染峰值</span><b>{controlStats.peakInfected} → {experimentStats.peakInfected}</b><small>{percentageChange(controlStats.peakInfected, experimentStats.peakInfected) === null ? "无法比较" : `减少 ${controlStats.peakInfected - experimentStats.peakInfected} 人，下降 ${percentageChange(controlStats.peakInfected, experimentStats.peakInfected)}%`}</small></div><div><span>死亡人数</span><b>{controlStats.dead} → {experimentStats.dead}</b><small>变化 {experimentStats.dead - controlStats.dead} 人</small></div></div><p className="spread-result__note">“免疫屏障”是本模块的科普反馈，不表示真实流行病学群体免疫阈值。</p></section>}
    </main>
    {coverageDialogOpen && <CoverageAdjustmentDialog value={coverageDraft} onChange={setCoverageDraft} onClose={() => setCoverageDialogOpen(false)} onRestart={restartWithCoverage} />}
  </section>;
}
