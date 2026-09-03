import { level3Assets } from "../../assets/immune/level3/level3Assets";

export interface LevelIntroSceneProps {
  onStart: () => void;
}

export function LevelIntroScene({ onStart }: LevelIntroSceneProps) {
  return (
    <section
      className="immune-level-scene immune-level-intro"
      aria-labelledby="level-one-title"
      style={{ backgroundImage: `url(${level3Assets.background})` }}
    >
      <div className="immune-level-copy">
        <h2 id="level-one-title">一次疫苗接种后，身体里发生了什么？</h2>
        <button type="button" onClick={onStart}>开始</button>
      </div>
    </section>
  );
}
