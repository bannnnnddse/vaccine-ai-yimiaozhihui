import {
  createContext,
  useContext,
  type CSSProperties,
  type ReactNode,
} from "react";
import type { MazeMap, MazeNode, MazeWallRegion } from "./mazeMap";
import { MAZE } from "./mazeMap";

const MazeMapContext = createContext<MazeMap>(MAZE);

export interface MazeBoardLayout {
  cellSize: number;
  width: number;
  height: number;
  left: number;
  top: number;
}

/** Uses one cell size on both axes and centers the board inside any viewport. */
export function getMazeBoardLayout(
  map: MazeMap,
  available: { width: number; height: number },
): MazeBoardLayout {
  const cellSize = Math.min(available.width / map.columns, available.height / map.rows);
  const width = cellSize * map.columns;
  const height = cellSize * map.rows;
  return {
    cellSize,
    width,
    height,
    left: (available.width - width) / 2,
    top: (available.height - height) / 2,
  };
}

function wallRegionStyle(region: MazeWallRegion, map: MazeMap): CSSProperties {
  return {
    position: "absolute",
    left: `${(region.col / map.columns) * 100}%`,
    top: `${(region.row / map.rows) * 100}%`,
    width: `${(region.width / map.columns) * 100}%`,
    height: `${(region.height / map.rows) * 100}%`,
  };
}

export function getMazeNodeStyle(node: MazeNode, map: MazeMap): CSSProperties {
  return {
    left: `${((node.col + 0.5) / map.columns) * 100}%`,
    top: `${((node.row + 0.5) / map.rows) * 100}%`,
    position: "absolute",
    transform: "translate(-50%, -50%)",
  };
}

export function useMazeNode(nodeId: string): MazeNode {
  const map = useMazeMap();
  const node = map.nodes[nodeId];
  if (!node) throw new Error(`Unknown maze node: ${nodeId}`);
  return node;
}

export function useMazeMap(): MazeMap {
  return useContext(MazeMapContext);
}

export interface MazeRendererProps {
  map: MazeMap;
  children: ReactNode;
}

/** Renders merged wall regions and actors from the same matrix topology. */
export function MazeRenderer({ map, children }: MazeRendererProps) {
  const mazeVariables = {
    position: "relative",
    "--maze-columns": map.columns,
    "--maze-rows": map.rows,
  } as CSSProperties;

  return (
    <MazeMapContext.Provider value={map}>
      <div
        className="immune-maze"
        data-maze-columns={map.columns}
        data-maze-rows={map.rows}
        data-square-cells="true"
        style={mazeVariables}
      >
        <div className="immune-maze__walls" aria-hidden="true">
          {map.wallRegions.map((region) => (
            <span
              key={`${region.row}:${region.col}:${region.width}:${region.height}`}
              className="immune-maze__wall"
              data-maze-wall-region
              style={wallRegionStyle(region, map)}
            />
          ))}
        </div>
        {children}
      </div>
    </MazeMapContext.Provider>
  );
}
