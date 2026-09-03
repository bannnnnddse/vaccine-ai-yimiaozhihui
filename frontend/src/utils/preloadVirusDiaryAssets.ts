import { immuneAssets } from "../assets/immune/immuneAssets";
import { level3Assets } from "../assets/immune/level3/level3Assets";

const MAX_CONCURRENT_REQUESTS = 2;
const FALLBACK_IDLE_DELAY_MS = 350;

type IdleDeadlineLike = {
  didTimeout: boolean;
  timeRemaining: () => number;
};

type IdleWindow = Window & typeof globalThis & {
  requestIdleCallback?: (
    callback: (deadline: IdleDeadlineLike) => void,
    options?: { timeout: number },
  ) => number;
};

/**
 * Uses the same imported URLs as the game, so Vite's hashed production assets
 * and the URLs placed in <img>/background-image share one browser cache entry.
 */
export const VIRUS_DIARY_IMAGE_BATCHES = [
  [
    level3Assets.background,
    immuneAssets.skinLayer,
    immuneAssets.needle,
    immuneAssets.injectionVirus,
    immuneAssets.virusExploring,
    immuneAssets.mazeDendriticCell,
  ],
  [
    immuneAssets.dendriticSideHolding,
    immuneAssets.dendriticCaptureArmUpperV2,
    immuneAssets.dendriticCaptureArmLowerV2,
    immuneAssets.antigenVirusStruggleLeftV2,
    immuneAssets.antigenVirusStruggleCenterV2,
    immuneAssets.antigenVirusStruggleRightV2,
    immuneAssets.dendriticCaptureStrainedV2,
    immuneAssets.dendriticCaptureSwallowV2,
    immuneAssets.antigenVirusSwallowV2,
    immuneAssets.dendriticSideSatisfied,
  ],
  [
    level3Assets.explorationBCell,
    level3Assets.explorationHelperTCell,
    level3Assets.explorationDendriticCell,
    level3Assets.explorationMacrophage,
    level3Assets.explorationRedBloodCell,
    level3Assets.helperTCell,
    level3Assets.helperTCellLabel,
    level3Assets.antigenPresentingCell,
    level3Assets.bCell,
    level3Assets.bCellPatrol,
    level3Assets.patrolVirus,
    level3Assets.memoryBCell,
    level3Assets.plasmaCell,
    level3Assets.antibody,
    level3Assets.redAntibody,
    level3Assets.virus,
    level3Assets.outcomeMacrophage,
    level3Assets.outcomeVirusRuptured,
    level3Assets.outcomeVirusNauseated,
    level3Assets.outcomeVirusDead,
    level3Assets.virusParticle,
    level3Assets.sleepingMemoryBCell,
    level3Assets.angryMemoryBCell,
  ],
] as const;

const requestedUrls = new Set<string>();
const activeImages = new Set<HTMLImageElement>();
let preloadStarted = false;

function scheduleWhenIdle(callback: () => void): void {
  const idleWindow = window as IdleWindow;
  if (typeof idleWindow.requestIdleCallback === "function") {
    idleWindow.requestIdleCallback(() => callback(), { timeout: 2_000 });
    return;
  }
  window.setTimeout(callback, FALLBACK_IDLE_DELAY_MS);
}

function preloadImage(src: string): Promise<void> {
  if (requestedUrls.has(src)) return Promise.resolve();
  requestedUrls.add(src);

  return new Promise((resolve) => {
    const image = new Image();
    activeImages.add(image);

    const settle = () => {
      activeImages.delete(image);
      resolve();
    };
    image.onload = settle;
    image.onerror = () => {
      if (import.meta.env.DEV) console.warn(`[virus-diary] Failed to preload image: ${src}`);
      settle();
    };
    image.src = src;
  });
}

async function preloadBatch(batch: readonly string[]): Promise<void> {
  for (let index = 0; index < batch.length; index += MAX_CONCURRENT_REQUESTS) {
    const group = batch.slice(index, index + MAX_CONCURRENT_REQUESTS);
    await Promise.all(group.map(preloadImage));
  }
}

function preloadBatchAt(index: number): void {
  const batch = VIRUS_DIARY_IMAGE_BATCHES[index];
  if (!batch) return;

  void preloadBatch(batch).finally(() => {
    scheduleWhenIdle(() => preloadBatchAt(index + 1));
  });
}

/** Starts once per page lifetime, including under React StrictMode. */
export function preloadVirusDiaryAssets(): void {
  if (preloadStarted || typeof window === "undefined" || typeof Image === "undefined") return;
  preloadStarted = true;
  scheduleWhenIdle(() => preloadBatchAt(0));
}
