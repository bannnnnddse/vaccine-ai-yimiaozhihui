export type MazeDirection = "up" | "down" | "left" | "right";

export const WALL = "1";
export const PASSAGE = "0";

export const MAZE_MATRIX = [
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

export interface MazeNode {
  id: string;
  col: number;
  row: number;
  exits: Partial<Record<MazeDirection, string>>;
}

export interface MazeWallRegion {
  col: number;
  row: number;
  width: number;
  height: number;
}

export interface MazeMap {
  columns: number;
  rows: number;
  matrix: readonly string[];
  nodes: Record<string, MazeNode>;
  wallRegions: readonly MazeWallRegion[];
}

const DIRECTIONS: ReadonlyArray<{
  direction: MazeDirection;
  rowDelta: number;
  colDelta: number;
}> = [
  { direction: "up", rowDelta: -1, colDelta: 0 },
  { direction: "down", rowDelta: 1, colDelta: 0 },
  { direction: "left", rowDelta: 0, colDelta: -1 },
  { direction: "right", rowDelta: 0, colDelta: 1 },
];

export function getMazeNodeId(row: number, col: number): string {
  return `r${row}c${col}`;
}

function mergeWallCells(matrix: readonly string[]): MazeWallRegion[] {
  const rows = matrix.length;
  const columns = matrix[0]?.length ?? 0;
  const visited = Array.from({ length: rows }, () => Array(columns).fill(false));
  const regions: MazeWallRegion[] = [];

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < columns; col += 1) {
      if (matrix[row][col] !== WALL || visited[row][col]) continue;

      let width = 1;
      while (
        col + width < columns
        && matrix[row][col + width] === WALL
        && !visited[row][col + width]
      ) width += 1;

      let height = 1;
      while (row + height < rows) {
        let canExtend = true;
        for (let offset = 0; offset < width; offset += 1) {
          if (
            matrix[row + height][col + offset] !== WALL
            || visited[row + height][col + offset]
          ) {
            canExtend = false;
            break;
          }
        }
        if (!canExtend) break;
        height += 1;
      }

      for (let mergedRow = row; mergedRow < row + height; mergedRow += 1) {
        for (let mergedCol = col; mergedCol < col + width; mergedCol += 1) {
          visited[mergedRow][mergedCol] = true;
        }
      }
      regions.push({ col, row, width, height });
    }
  }

  return regions;
}

function buildMaze(matrix: readonly string[]): MazeMap {
  const rows = matrix.length;
  const columns = matrix[0]?.length ?? 0;
  const nodes: Record<string, MazeNode> = {};

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < columns; col += 1) {
      if (matrix[row][col] !== PASSAGE) continue;
      const id = getMazeNodeId(row, col);
      nodes[id] = { id, row, col, exits: {} };
    }
  }

  for (const node of Object.values(nodes)) {
    for (const { direction, rowDelta, colDelta } of DIRECTIONS) {
      const destination = getMazeNodeId(node.row + rowDelta, node.col + colDelta);
      if (nodes[destination]) node.exits[direction] = destination;
    }
  }

  return {
    columns,
    rows,
    matrix,
    nodes,
    wallRegions: mergeWallCells(matrix),
  };
}

// The dendritic cell begins at the virus's former entry point; the virus is
// one passage cell below it so the opening frame reads as an imminent chase.
export const DENDRITIC_START = getMazeNodeId(1, 1);
export const VIRUS_START = getMazeNodeId(2, 1);
export const MAZE: MazeMap = buildMaze(MAZE_MATRIX);

export function getFarthestReachableNode(
  map: MazeMap,
  id: string,
  direction: MazeDirection,
): string {
  return getDirectionalPath(map, id, direction).at(-1) ?? id;
}

/** Includes the starting node and every passage cell crossed before the wall. */
export function getDirectionalPath(
  map: MazeMap,
  id: string,
  direction: MazeDirection,
): string[] {
  const path = [id];
  let current = id;
  let next = map.nodes[current]?.exits[direction];

  while (next) {
    current = next;
    path.push(current);
    next = map.nodes[current].exits[direction];
  }

  return path;
}

const OPPOSITE_DIRECTIONS: Record<MazeDirection, MazeDirection> = {
  up: "down",
  down: "up",
  left: "right",
  right: "left",
};

/** Returns deterministic validation messages for authored matrix maps. */
export function validateMaze(map: MazeMap): string[] {
  const errors: string[] = [];

  if (map.rows !== map.matrix.length) errors.push("Row count does not match matrix");
  if (map.matrix.some((row) => row.length !== map.columns)) {
    errors.push("Column count does not match matrix");
  }
  if (map.matrix.some((row) => [...row].some((cell) => cell !== WALL && cell !== PASSAGE))) {
    errors.push("Matrix contains a cell other than 0 or 1");
  }
  if (
    map.matrix[0]?.includes(PASSAGE)
    || map.matrix.at(-1)?.includes(PASSAGE)
    || map.matrix.some((row) => row[0] === PASSAGE || row.at(-1) === PASSAGE)
  ) errors.push("Outer boundary must be closed by walls");

  for (let row = 0; row < map.rows; row += 1) {
    for (let col = 0; col < map.columns; col += 1) {
      const id = getMazeNodeId(row, col);
      const isPassage = map.matrix[row]?.[col] === PASSAGE;
      if (isPassage !== Boolean(map.nodes[id])) errors.push(`Node mismatch at ${row},${col}`);
    }
  }

  for (const node of Object.values(map.nodes)) {
    for (const [direction, destinationId] of Object.entries(node.exits) as [
      MazeDirection,
      string,
    ][]) {
      const destination = map.nodes[destinationId];
      if (!destination) {
        errors.push(`Exit ${node.id}:${direction} has no passage destination`);
        continue;
      }
      if (destination.exits[OPPOSITE_DIRECTIONS[direction]] !== node.id) {
        errors.push(`Exit ${node.id}:${direction} is not reciprocal`);
      }
    }
  }

  return errors;
}
