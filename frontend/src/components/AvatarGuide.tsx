import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import type { DigitalHumanState } from "../hooks/useDigitalHumanInteraction";
import { createAvatarGazeRuntime, type AvatarGazeState } from "./avatarGazeState";

const AVATAR_IMAGES = {
  rest: "/assets/avatar/normal.png",
  blink: "/assets/avatar/close-eyes.png",
} as const;

interface AvatarGuideProps {
  state?: DigitalHumanState;
  interactive?: boolean;
  panelOpen?: boolean;
  onActivate?: () => void;
  media?: ReactNode;
}

export function AvatarGuide({ state = "idle", interactive = false, panelOpen = false, onActivate, media }: AvatarGuideProps) {
  const [gaze, setGaze] = useState<AvatarGazeState>({
    visualState: "rest",
  });

  useEffect(() => {
    if (media || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const runtime = createAvatarGazeRuntime({ onStateChange: setGaze });
    const onPointerMove = () => runtime.pointerMoved();
    window.addEventListener("pointermove", onPointerMove);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      runtime.dispose();
    };
  }, [media]);

  const image = AVATAR_IMAGES[gaze.visualState];
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!interactive || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    onActivate?.();
  };

  return (
    <aside className={`avatar-guide avatar-guide--${state}${interactive ? " is-interactive" : ""}`} aria-label="疫苗科普数字人讲解员">
      <div
        className="avatar-stage"
        role={interactive ? "button" : undefined}
        tabIndex={interactive ? 0 : undefined}
        aria-label={interactive ? "打开数字人快捷提示" : undefined}
        aria-expanded={interactive ? panelOpen : undefined}
        data-digital-human-trigger={interactive ? "true" : undefined}
        onClick={interactive ? onActivate : undefined}
        onKeyDown={handleKeyDown}
      >
        <div className="avatar-stage__halo" aria-hidden="true" />
        <div className="avatar-media-slot">
          {media ?? <img src={image} alt="亲切的女性疫苗科普数字讲解员" />}
        </div>
      </div>
    </aside>
  );
}
