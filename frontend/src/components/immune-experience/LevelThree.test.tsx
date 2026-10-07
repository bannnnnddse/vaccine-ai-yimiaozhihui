import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { existsSync, readFileSync } from "node:fs";
import {
  LevelThree,
  ACTIVATION_CAPTION_FADE_DURATION_MS,
  ACTIVATION_CAPTION_SCENE_DURATION_MS,
  INTERLUDE_CAPTION_HOLD_DURATION_MS,
  OPENING_HOLD_DURATION_MS,
  canAdvanceInterludeCaption,
  getLevelThreeActivationDuration,
  getLevelThreeMission,
  getLevelThreeOpeningStage,
  shouldShowLevelThreeSuccess,
} from "./LevelThree";
import { level3Assets } from "../../assets/immune/level3/level3Assets";

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

describe("LevelThree", () => {
  it("starts the three-part typed lymph narration with no cells", () => {
    const markup = renderToStaticMarkup(<LevelThree />);

    expect(markup).toContain("淋巴液免疫识别");
    expect(markup).not.toContain("data-cell-id=");
    expect(markup).not.toContain("immune-level-three-opening\"");
  });

  it("includes three narration stages before it reveals the cells", () => {
    const source = readFileSync(new URL("./LevelThree.tsx", import.meta.url), "utf8");
    expect(OPENING_HOLD_DURATION_MS).toBe(30_000);
    expect(getLevelThreeOpeningStage(0)).toBe("context");
    expect(getLevelThreeOpeningStage(3999)).toBe("context");
    expect(getLevelThreeOpeningStage(4000)).toBe("arrival");
    expect(getLevelThreeOpeningStage(6999)).toBe("arrival");
    expect(getLevelThreeOpeningStage(7000)).toBe("prompt");
    expect(getLevelThreeOpeningStage(9999)).toBe("prompt");
    expect(getLevelThreeOpeningStage(10000)).toBe("ready");
    expect(source).toContain("吞噬了，\\n他从你身上提取出了抗原标志物并呈递");
    expect(source).toContain("淋巴组织内存在着大量免疫细胞，看看谁能提供帮助？");
  });

  it("keeps the final word of the context narration on its second line", () => {
    const contextCaptionRule = styles.match(
      /\.immune-level-three-opening-caption\.is-context\s*{([^}]*)}/s,
    )?.[1] ?? "";

    expect(contextCaptionRule).toContain("1040px");
    expect(contextCaptionRule).toContain("white-space: pre-line");
  });

  it("gives both antibody-generation captions a translucent drop-and-fade bubble", () => {
    const captionRule = styles.match(/\.immune-antibody-caption\s*{([^}]*)}/s)?.[1] ?? "";
    const generationRule = styles.match(
      /\.immune-antibody-caption\.is-antibody, \.immune-antibody-caption\.is-antibody-drift\s*{([^}]*)}/s,
    )?.[1] ?? "";

    expect(captionRule).toContain("background: rgba(255,255,255,.7)");
    expect(captionRule).toContain("border-radius: 20px");
    expect(generationRule).toContain("immune-activation-caption-drop");
    expect(generationRule).toContain("immune-antibody-caption-opacity-fade-out");
  });

  it("uses the approved timing for each activation phase", () => {
    expect(getLevelThreeActivationDuration("tCellFound")).toBe(1400);
    expect(getLevelThreeActivationDuration("focus-b-cell")).toBe(700);
    expect(getLevelThreeActivationDuration("t-cell-contact")).toBe(1800);
    expect(ACTIVATION_CAPTION_SCENE_DURATION_MS).toBe(8000);
    expect(ACTIVATION_CAPTION_FADE_DURATION_MS).toBe(400);
    expect(getLevelThreeActivationDuration("t-cell-contact-hold")).toBeNull();
    expect(getLevelThreeActivationDuration("antigen-presentation")).toBe(1600);
    expect(getLevelThreeActivationDuration("antigen-presentation-hold")).toBeNull();
    expect(getLevelThreeActivationDuration("differentiation")).toBe(3000);
    expect(getLevelThreeActivationDuration("plasma-ready")).toBe(400);
    expect(getLevelThreeActivationDuration("antibody")).toBe(4500);
    expect(getLevelThreeActivationDuration("antibody-drift")).toBeNull();
    expect(getLevelThreeActivationDuration("virus-entry")).toBe(3000);
    expect(getLevelThreeActivationDuration("antibody-binding")).toBe(2600);
    expect(getLevelThreeActivationDuration("neutralized")).toBeNull();
    expect(getLevelThreeActivationDuration("outcome-transition")).toBe(900);
    expect(getLevelThreeActivationDuration("outcome-scenes")).toBe(8000);
    expect(getLevelThreeActivationDuration("outcome-exit")).toBe(1200);
    expect(getLevelThreeActivationDuration("interlude-pause")).toBe(500);
    expect(getLevelThreeActivationDuration("however-caption")).toBeNull();
    expect(getLevelThreeActivationDuration("rechallenge-caption")).toBeNull();
    expect(INTERLUDE_CAPTION_HOLD_DURATION_MS).toBe(30_000);
    expect(getLevelThreeActivationDuration("memory-recall")).toBe(3600);
    expect(getLevelThreeActivationDuration("memory-awakening")).toBe(600);
    expect(getLevelThreeActivationDuration("memory-antibody-storm")).toBe(4500);
    expect(getLevelThreeActivationDuration("iris-focus")).toBe(1400);
    expect(getLevelThreeActivationDuration("iris-hold")).toBe(1000);
    expect(getLevelThreeActivationDuration("iris-close")).toBe(650);
    expect(getLevelThreeActivationDuration("blackout")).toBeNull();
  });

  it("updates the mission for outcome scenes and memory recall, then hides it in blackout", () => {
    expect(getLevelThreeMission("outcome-scenes")).toBe("抗体标记后，病毒还会经历什么？");
    expect(getLevelThreeMission("memory-recall")).toBe("记忆 B 细胞正在快速启动二次应答……");
    expect(getLevelThreeMission("iris-close")).toBe("记忆 B 细胞正在快速启动二次应答……");
    expect(getLevelThreeMission("blackout")).toBeNull();
  });

  it("keeps the old success panel only through neutralization", () => {
    expect(shouldShowLevelThreeSuccess("antibody")).toBe(true);
    expect(shouldShowLevelThreeSuccess("neutralized")).toBe(true);
    expect(shouldShowLevelThreeSuccess("outcome-transition")).toBe(false);
    expect(shouldShowLevelThreeSuccess("outcome-scenes")).toBe(false);
    expect(shouldShowLevelThreeSuccess("blackout")).toBe(false);
  });

  it("allows clicks to advance only the two interlude captions", () => {
    expect(canAdvanceInterludeCaption("however-caption")).toBe(true);
    expect(canAdvanceInterludeCaption("rechallenge-caption")).toBe(true);
    expect(canAdvanceInterludeCaption("interlude-pause")).toBe(false);
    expect(canAdvanceInterludeCaption("memory-recall")).toBe(false);
  });

  it("uses the supplied level-three assets and transparent PNG cell cutouts", () => {
    expect(Object.keys(level3Assets).sort()).toEqual([
      "angryMemoryBCell",
      "antibody",
      "antigenPresentingCell",
      "bCell",
      "bCellPatrol",
      "background",
      "dendriticCell",
      "explorationBCell",
      "explorationDendriticCell",
      "explorationHelperTCell",
      "explorationMacrophage",
      "explorationRedBloodCell",
      "helperTCell",
      "helperTCellContact",
      "helperTCellLabel",
      "macrophage",
      "memoryBCell",
      "outcomeMacrophage",
      "outcomeVirusDead",
      "outcomeVirusNauseated",
      "outcomeVirusRuptured",
      "patrolVirus",
      "plasmaCell",
      "redAntibody",
      "redBloodCell",
      "sleepingMemoryBCell",
      "virus",
      "virusParticle",
    ]);

    for (const relativePath of [
      "../../assets/immune/level3/antibody.svg",
      "../../assets/immune/level3/antibody-red.svg",
      "../../assets/immune/level3/antigen-presenting-cell.png",
      "../../assets/immune/level3/b-cell.png",
      "../../assets/immune/level3/b-cell-patrol.png",
      "../../assets/immune/level3/lymph-background.png",
      "../../assets/immune/level3/dendritic-cell.png",
      "../../assets/immune/level3/helper-t-cell.png",
      "../../assets/immune/level3/helper-t-cell-contact.png",
      "../../assets/immune/level3/helper-t-cell-label.png",
      "../../assets/immune/level3/macrophage.svg",
      "../../assets/immune/level3/memory-b-cell.png",
      "../../assets/immune/level3/patrol-virus.png",
      "../../assets/immune/level3/patrol-virus-transparent.png",
      "../../assets/immune/level3/plasma-cell.png",
      "../../assets/immune/level3/red-blood-cell.png",
      "../../assets/immune/level3/virus.png",
      "../../assets/immune/level3/outcomes/macrophage-side-open-mouth.png",
      "../../assets/immune/level3/outcomes/virus-ruptured.png",
      "../../assets/immune/level3/outcomes/virus-nauseated.png",
      "../../assets/immune/level3/outcomes/virus-dead.png",
    ]) {
      expect(existsSync(new URL(relativePath, import.meta.url))).toBe(true);
    }

    for (const relativePath of [
      "../../assets/immune/level3/b-cell.png",
      "../../assets/immune/level3/b-cell-patrol.png",
      "../../assets/immune/level3/helper-t-cell.png",
      "../../assets/immune/level3/helper-t-cell-contact.png",
      "../../assets/immune/level3/antigen-presenting-cell.png",
      "../../assets/immune/level3/memory-b-cell.png",
      "../../assets/immune/level3/plasma-cell.png",
      "../../assets/immune/level3/patrol-virus-transparent.png",
      "../../assets/immune/level3/red-blood-cell.png",
      "../../assets/immune/level3/virus.png",
      "../../assets/immune/level3/outcomes/macrophage-side-open-mouth.png",
      "../../assets/immune/level3/outcomes/virus-ruptured.png",
      "../../assets/immune/level3/outcomes/virus-nauseated.png",
      "../../assets/immune/level3/outcomes/virus-dead.png",
    ]) {
      const png = readFileSync(new URL(relativePath, import.meta.url));
      expect(png.readUInt8(25)).toBe(6);
    }

    expect(readFileSync(new URL("../../assets/immune/level3/antibody-red.svg", import.meta.url), "utf8"))
      .toContain("#e65b67");
  });

  it("provides dedicated activation and differentiation components", () => {
    expect(existsSync(new URL("./BCellActivationSequence.tsx", import.meta.url))).toBe(true);
    expect(existsSync(new URL("./BCellDifferentiation.tsx", import.meta.url))).toBe(true);
    expect(existsSync(new URL("./VirusNeutralization.tsx", import.meta.url))).toBe(true);
  });

  it("exposes enlarged exploration sizes for all five cell assets", () => {
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

    expect(styles).toMatch(/\.immune-level-three\s*{[^}]*--immune-exploration-cell-size:\s*clamp\(116px,\s*15vw,\s*198px\)[^}]*--immune-exploration-large-cell-size:\s*clamp\(128px,\s*16\.5vw,\s*215px\)[^}]*--immune-exploration-red-cell-size:\s*clamp\(135px,\s*17\.5vw,\s*230px\)/s);
    expect(styles).toMatch(/\.immune-level-three-cell\s*{[^}]*width:\s*var\(--immune-exploration-cell-size\)/s);
    expect(styles).toMatch(/\.immune-level-three-cell\.is-dendritic-cell,\s*\.immune-level-three-cell\.is-macrophage\s*{[^}]*width:\s*var\(--immune-exploration-large-cell-size\)/s);
    expect(styles).toMatch(/\.immune-level-three-cell\.is-red-blood-cell\s*{[^}]*width:\s*var\(--immune-exploration-red-cell-size\)/s);
  });
});
