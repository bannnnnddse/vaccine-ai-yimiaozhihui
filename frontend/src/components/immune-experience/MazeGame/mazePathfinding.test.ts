import { describe, expect, it } from "vitest";
import { DENDRITIC_START, MAZE, VIRUS_START } from "./mazeMap";
import { getShortestPath } from "./mazePathfinding";

describe("matrix maze pathfinding", () => {
  it("finds a connected shortest route between the adjacent opening actors", () => {
    const path = getShortestPath(MAZE, DENDRITIC_START, VIRUS_START);

    expect(path[0]).toBe(DENDRITIC_START);
    expect(path.at(-1)).toBe(VIRUS_START);
    expect(path).toEqual(["r1c1", "r2c1"]);
  });

  it("never includes a wall cell in its BFS route", () => {
    const matrix = (MAZE as typeof MAZE & { matrix: readonly string[] }).matrix;
    const path = getShortestPath(MAZE, DENDRITIC_START, VIRUS_START);

    for (const nodeId of path) {
      const node = MAZE.nodes[nodeId];
      expect(matrix[node.row][node.col]).toBe("0");
    }
  });
});
