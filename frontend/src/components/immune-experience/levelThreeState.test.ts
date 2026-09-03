import { describe, expect, it } from "vitest";
import {
  INITIAL_LEVEL_THREE_STATE,
  createLevelThreeCells,
  transitionLevelThree,
  type LevelThreeState,
} from "./levelThreeState";

describe("level three state", () => {
  it("starts in exploration with five separated cell entities", () => {
    const cells = createLevelThreeCells(() => 0.42);

    expect(INITIAL_LEVEL_THREE_STATE.phase).toBe("exploring");
    expect(cells.map((cell) => cell.id).sort()).toEqual([
      "b-cell",
      "dendritic-cell",
      "helper-t-cell",
      "macrophage",
      "red-blood-cell",
    ]);
    expect(new Set(cells.map((cell) => `${cell.position.x}:${cell.position.y}`)).size).toBe(5);
    expect(cells.find((cell) => cell.id === "b-cell")?.position).toEqual({ x: 50, y: 50 });
  });

  it("lets the helper T cell start the next scene after B cell inspection", () => {
    const afterBCell = transitionLevelThree(INITIAL_LEVEL_THREE_STATE, {
      type: "select-cell",
      cellId: "b-cell",
    });

    expect(afterBCell.phase).toBe("bCellFound");
    expect(afterBCell.selectedCellId).toBe("b-cell");
    expect(afterBCell.revealedCellIds).toContain("b-cell");

    const activated = transitionLevelThree(afterBCell, {
      type: "select-cell",
      cellId: "helper-t-cell",
    });
    expect(activated.phase).toBe("tCellFound");
    expect(activated.selectedCellId).toBe("helper-t-cell");
  });

  it("does not require a second selection after the helper T cell is found", () => {
    const afterTCell = transitionLevelThree(INITIAL_LEVEL_THREE_STATE, {
      type: "select-cell",
      cellId: "helper-t-cell",
    });

    expect(afterTCell.phase).toBe("tCellFound");
    expect(afterTCell.selectedCellId).toBe("helper-t-cell");

    const activated = transitionLevelThree(afterTCell, {
      type: "select-cell",
      cellId: "b-cell",
    });
    expect(activated).toBe(afterTCell);
  });

  it("keeps the current immune progress when a distractor is inspected", () => {
    const bCellFound = transitionLevelThree(INITIAL_LEVEL_THREE_STATE, {
      type: "select-cell",
      cellId: "b-cell",
    });
    const afterMacrophage = transitionLevelThree(bCellFound, {
      type: "select-cell",
      cellId: "macrophage",
    });

    expect(afterMacrophage.phase).toBe("bCellFound");
    expect(afterMacrophage.selectedCellId).toBe("macrophage");
    expect(afterMacrophage.revealedCellIds).toEqual(["b-cell", "macrophage"]);
  });

  it("advances through the complete activation and differentiation sequence", () => {
    const phases = [
      "focus-b-cell",
      "t-cell-contact",
      "t-cell-contact-hold",
      "antigen-presentation",
      "antigen-presentation-hold",
      "b-cell-patrol-intro",
      "b-cell-patrol",
      "b-cell-patrol-caught",
      "differentiation",
      "plasma-ready",
      "antibody",
      "antibody-drift",
      "virus-entry",
      "antibody-binding",
      "neutralized",
    ] as const;
    let state: LevelThreeState = { ...INITIAL_LEVEL_THREE_STATE, phase: phases[0] };

    for (const expectedPhase of phases.slice(1)) {
      state = transitionLevelThree(state, { type: "advance-activation" });
      expect(state.phase).toBe(expectedPhase);
    }
  });

  it("holds each contact scene before advancing activation", () => {
    const transitions = [
      ["t-cell-contact", "t-cell-contact-hold"],
      ["t-cell-contact-hold", "antigen-presentation"],
      ["antigen-presentation", "antigen-presentation-hold"],
      ["antigen-presentation-hold", "b-cell-patrol-intro"],
    ] as const;

    for (const [phase, expectedPhase] of transitions) {
      const state = transitionLevelThree(
        { ...INITIAL_LEVEL_THREE_STATE, phase },
        { type: "advance-activation" },
      );
      expect(state.phase).toBe(expectedPhase);
    }
  });

  it("advances through the complete outcome and memory-recall timeline", () => {
    const phases = [];
    let state: LevelThreeState = { ...INITIAL_LEVEL_THREE_STATE, phase: "neutralized" };

    for (let index = 0; index < 13; index += 1) {
      state = transitionLevelThree(state, { type: "advance-activation" });
      phases.push(state.phase);
    }

    expect(phases).toEqual([
      "outcome-transition",
      "outcome-scenes",
      "outcome-exit",
      "interlude-pause",
      "however-caption",
      "rechallenge-caption",
      "memory-recall",
      "memory-awakening",
      "memory-antibody-storm",
      "iris-focus",
      "iris-hold",
      "iris-close",
      "blackout",
    ]);
    expect(transitionLevelThree(state, { type: "advance-activation" })).toBe(state);
  });
});
