import { useEffect, useMemo, useState } from "react";
import "./TextType.css";

interface TextTypeProps {
  text: string | string[];
  typingSpeed?: number;
  pauseDuration?: number;
  loop?: boolean;
  showCursor?: boolean;
  className?: string;
  cursorCharacter?: string;
  onComplete?: () => void;
}

export function TextType({
  text,
  typingSpeed = 70,
  pauseDuration = 1_500,
  loop = false,
  showCursor = true,
  className = "",
  cursorCharacter = "|",
  onComplete,
}: TextTypeProps) {
  const phrases = useMemo(() => {
    const values = Array.isArray(text) ? text : [text];
    return values.length > 0 ? values : [""];
  }, [text]);
  const [displayedText, setDisplayedText] = useState("");
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(() => (
    typeof window !== "undefined"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ));

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setPrefersReducedMotion(mediaQuery.matches);
    updatePreference();
    mediaQuery.addEventListener("change", updatePreference);

    return () => mediaQuery.removeEventListener("change", updatePreference);
  }, []);

  useEffect(() => {
    if (prefersReducedMotion) {
      setDisplayedText(phrases[0]);
      onComplete?.();
      return undefined;
    }

    let cancelled = false;
    let phraseIndex = 0;
    let characterIndex = 0;
    let timer: number | undefined;

    const typeNextCharacter = () => {
      if (cancelled) return;

      const phrase = phrases[phraseIndex];
      if (characterIndex < phrase.length) {
        characterIndex += 1;
        setDisplayedText(phrase.slice(0, characterIndex));
        timer = window.setTimeout(typeNextCharacter, typingSpeed);
        return;
      }

      const hasNextPhrase = phraseIndex < phrases.length - 1;
      if (!hasNextPhrase && !loop) {
        onComplete?.();
        return;
      }

      timer = window.setTimeout(() => {
        phraseIndex = hasNextPhrase ? phraseIndex + 1 : 0;
        characterIndex = 0;
        setDisplayedText("");
        typeNextCharacter();
      }, pauseDuration);
    };

    setDisplayedText("");
    timer = window.setTimeout(typeNextCharacter, typingSpeed);

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [loop, onComplete, pauseDuration, phrases, prefersReducedMotion, typingSpeed]);

  const rootClassName = ["text-type", className].filter(Boolean).join(" ");

  return (
    <span className={rootClassName} aria-label={phrases.join(" ")}>
      <span aria-hidden="true">{displayedText}</span>
      {showCursor && !prefersReducedMotion && (
        <span className="text-type__cursor" aria-hidden="true">{cursorCharacter}</span>
      )}
    </span>
  );
}
