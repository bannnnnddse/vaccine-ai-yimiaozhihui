import { describe, expect, it } from "vitest";
import {
  DENDRITIC_START,
  MAZE,
  VIRUS_START,
  getFarthestReachableNode,
  getDirectionalPath,
  validateMaze,
} from "./mazeMap";
import { getDirectionFromKey, getSwipeDirection } from "./mazeMovement";

const EXPECTED_MATRIX = [
  "111111111111111111111",
  "100000100000001000001",
  "101110101111101011101",
  "101000100010001010001",
  "101011111010111010111",
  "100010000010100010001",
  "111010111110101111101",
  "100010100000100000101",
  "101110101111111110101",
  "101000000000000010001",
  "101111101011111011101",
  "100000001000001000001",
  "111111111111111111111",
] as const;

describe("maze movement", () => {
  it("maps desktop keys and dominant-axis swipes to one direction", () => {
    expect(getDirectionFromKey("A")).toBe("left");
    expect(getDirectionFromKey("D")).toBe("right");
    expect(getDirectionFromKey("W")).toBe("up");
    expect(getDirectionFromKey("S")).toBe("down");
    expect(getDirectionFromKey("ArrowLeft")).toBe("left");
    expect(getDirectionFromKey("ArrowRight")).toBe("right");
    expect(getDirectionFromKey("ArrowUp")).toBe("up");
    expect(getDirectionFromKey("ArrowDown")).toBe("down");
    expect(getSwipeDirection({ x: 5, y: -40 })).toBe("up");
    expect(getSwipeDirection({ x: 5, y: 40 })).toBe("down");
    expect(getSwipeDirection({ x: 0, y: 0 })).toBeNull();
  });

  it("uses the supplied 21 by 13 closed matrix as the topology source", () => {
    expect(MAZE.columns).toBe(21);
    expect(MAZE.rows).toBe(13);
    expect((MAZE as typeof MAZE & { matrix: readonly string[] }).matrix).toEqual(EXPECTED_MATRIX);
    expect(validateMaze(MAZE)).toEqual([]);
    expect(MAZE.nodes[VIRUS_START]).toMatchObject({ row: 2, col: 1 });
    expect(MAZE.nodes[DENDRITIC_START]).toMatchObject({ row: 1, col: 1 });
  });

  it("slides to the farthest zero cell without crossing a wall or auto-turning", () => {
    expect(getFarthestReachableNode(MAZE, VIRUS_START, "right")).toBe("r2c1");
    expect(getFarthestReachableNode(MAZE, VIRUS_START, "down")).toBe("r5c1");
    expect(getFarthestReachableNode(MAZE, "r1c5", "down")).toBe("r3c5");
    expect(getFarthestReachableNode(MAZE, "r1c5", "right")).toBe("r1c5");
  });

  it("returns every passage node crossed by one directional slide", () => {
    expect(getDirectionalPath(MAZE, "r3c7", "right")).toEqual([
      "r3c7",
      "r3c8",
      "r3c9",
    ]);
    expect(getDirectionalPath(MAZE, "r3c5", "up")).toEqual(["r3c5", "r2c5", "r1c5"]);
  });
});
