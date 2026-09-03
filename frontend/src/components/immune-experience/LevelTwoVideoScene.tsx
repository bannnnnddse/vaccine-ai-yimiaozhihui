import { AntigenPresentationScene } from "./AntigenPresentationScene";

export interface LevelTwoVideoSceneProps {
  onEnded: () => void;
  transitioning?: boolean;
}

export function LevelTwoVideoScene({ onEnded, transitioning = false }: LevelTwoVideoSceneProps) {
  return (
    <section className={`immune-level-two-video-scene${transitioning ? " immune-is-transitioning" : ""}`}>
      <h2 className="sr-only">树突状细胞抗原呈递场景</h2>
      <AntigenPresentationScene onEnded={onEnded} />
    </section>
  );
}
