import type { MazeMap } from "./mazeMap";

/** Returns the shortest directed route between two maze nodes, including both ends. */
export function getShortestPath(map: MazeMap, from: string, to: string): string[] {
  if (!map.nodes[from] || !map.nodes[to]) {
    return [from];
  }

  const queue = [[from]];
  const seen = new Set([from]);

  while (queue.length) {
    const path = queue.shift()!;
    const id = path.at(-1)!;
    if (id === to) {
      return path;
    }

    for (const next of Object.values(map.nodes[id].exits)) {
      if (next && !seen.has(next)) {
        seen.add(next);
        queue.push([...path, next]);
      }
    }
  }

  return [from];
}
