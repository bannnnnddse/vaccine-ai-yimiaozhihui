import type { CSSProperties } from "react";
import { immuneAssets } from "../../../assets/immune/immuneAssets";
import { getMazeNodeStyle, useMazeMap, useMazeNode } from "./MazeRenderer";

export type VirusVisualState = "idle" | "moving" | "captured";

export interface VirusPlayerProps {
  node: string;
  visualState?: VirusVisualState;
  motionDurationMs?: number;
}

/** Visual-only virus marker. Movement and input belong to the maze scene. */
export function VirusPlayer({ node: nodeId, visualState = "idle", motionDurationMs = 230 }: VirusPlayerProps) {
  const node = useMazeNode(nodeId);
  const style = {
    ...getMazeNodeStyle(node, useMazeMap()),
    "--immune-maze-motion-duration": `${motionDurationMs}ms`,
  } as CSSProperties;

  return (
    <div
      className={`immune-maze__virus is-${visualState}`}
      data-maze-virus={visualState}
      data-maze-node={nodeId}
      style={style}
      role="img"
      aria-label="病毒"
    >
      <img src={immuneAssets.virusExploring} alt="" aria-hidden="true" draggable={false} />
    </div>
  );
}
