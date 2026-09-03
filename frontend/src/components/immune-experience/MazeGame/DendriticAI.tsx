import type { CSSProperties } from "react";
import { immuneAssets } from "../../../assets/immune/immuneAssets";
import { getMazeNodeStyle, useMazeMap, useMazeNode } from "./MazeRenderer";

export type DendriticVisualState = "idle" | "waiting" | "chasing" | "captured";

export interface DendriticAIProps {
  node: string;
  visualState?: DendriticVisualState;
  motionDurationMs?: number;
}

/** Visual-only dendritic cell marker. Pursuit scheduling belongs to the maze scene. */
export function DendriticAI({ node: nodeId, visualState = "idle", motionDurationMs = 180 }: DendriticAIProps) {
  const node = useMazeNode(nodeId);
  const style = {
    ...getMazeNodeStyle(node, useMazeMap()),
    "--immune-maze-motion-duration": `${motionDurationMs}ms`,
    transform: "translate(calc(-50% + var(--immune-maze-dendritic-offset-x)), calc(-50% + var(--immune-maze-dendritic-offset-y)))",
  } as CSSProperties;

  return (
    <div
      className={`immune-maze__dendritic is-${visualState}`}
      data-maze-dendritic={visualState}
      data-maze-node={nodeId}
      style={style}
      role="img"
      aria-label="树突状细胞"
    >
      <img src={immuneAssets.mazeDendriticCell} alt="" aria-hidden="true" draggable={false} />
    </div>
  );
}
