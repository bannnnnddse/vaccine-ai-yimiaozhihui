import type { MazeDirection } from "./mazeMap";

export interface SwipeDelta {
  x: number;
  y: number;
}

const KEY_DIRECTIONS: Record<string, MazeDirection> = {
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  ArrowUp: "up",
  a: "left",
  d: "right",
  s: "down",
  w: "up",
};

export function getDirectionFromKey(key: string): MazeDirection | null {
  return KEY_DIRECTIONS[key.length === 1 ? key.toLowerCase() : key] ?? null;
}

export function getSwipeDirection({ x, y }: SwipeDelta): MazeDirection | null {
  if (x === 0 && y === 0) {
    return null;
  }

  if (Math.abs(x) >= Math.abs(y)) {
    return x > 0 ? "right" : "left";
  }

  return y > 0 ? "down" : "up";
}
