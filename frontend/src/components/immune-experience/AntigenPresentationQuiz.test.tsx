import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { level3Assets } from "../../assets/immune/level3/level3Assets";
import { AntigenPresentationQuiz } from "./AntigenPresentationQuiz";

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  return {
    ...react,
    useEffect: () => undefined,
    useRef: () => ({ current: null }),
  };
});

vi.mock("./useReducedMotion", () => ({ useReducedMotion: () => false }));

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

function buttons(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [
    ...(node.type === "button" ? [node] : []),
    ...Children.toArray(node.props.children as ReactNode).flatMap(buttons),
  ];
}

describe("AntigenPresentationQuiz", () => {
  it("renders the exact question and three vertical semantic answer cards", () => {
    const markup = renderToStaticMarkup(
      <AntigenPresentationQuiz feedback={null} selectedAnswer={null} onAnswer={() => undefined} />,
    );

    expect(markup).toContain("树突状细胞展示抗原的目的是？");
    expect(markup).toContain("A.为了让T细胞识别");
    expect(markup).toContain("B. 为了被抗体直接攻击");
    expect(markup).toContain("C. 为了逃避免疫系统");
    expect((markup.match(/<button/g) ?? [])).toHaveLength(3);
    expect(markup).not.toContain("background-image");
    expect(markup).toContain(level3Assets.background);
    expect(markup).toContain("immune-level-two-quiz-background");
    expect(styles).toMatch(/\.immune-level-two-quiz-background\s*{[^}]*filter:\s*blur\(var\(--immune-level-two-background-blur\)\)/s);
    expect(styles).toMatch(/\.immune-level-two-quiz::before\s*{[^}]*background:\s*rgba\(255,255,255,\.65\)[^}]*backdrop-filter:\s*blur\(3px\)/s);
  });

  it("calls the chosen answer once and locks every card during feedback", () => {
    const onAnswer = vi.fn();
    const idle = AntigenPresentationQuiz({ feedback: null, selectedAnswer: null, onAnswer });
    const idleButtons = buttons(idle);

    (idleButtons[1].props.onClick as () => void)();
    expect(onAnswer).toHaveBeenCalledExactlyOnceWith("B");

    const lockedMarkup = renderToStaticMarkup(
      <AntigenPresentationQuiz feedback="incorrect" selectedAnswer="B" onAnswer={onAnswer} />,
    );
    expect((lockedMarkup.match(/ disabled=""/g) ?? [])).toHaveLength(3);
    expect(lockedMarkup).toContain("不对哦，再想想...");
    expect(lockedMarkup).toContain('aria-live="assertive"');
  });

  it("renders the exact correct feedback and marks the selected answer", () => {
    const markup = renderToStaticMarkup(
      <AntigenPresentationQuiz feedback="correct" selectedAnswer="A" onAnswer={() => undefined} />,
    );

    expect(markup).toContain("正确！T细胞正在赶来");
    expect(markup).toContain('data-selected="true"');
  });

  it("uses horizontal cards, spring hover, touch press, triple shake, and reduced motion", () => {
    expect(styles).toMatch(/\.immune-level-two-answer-row\s*{[^}]*display:\s*flex[^}]*justify-content:\s*center/s);
    expect(styles).toMatch(/\.immune-level-two-answer-card:nth-child\(1\):hover[^}]*rotate\(-/s);
    expect(styles).toMatch(/\.immune-level-two-answer-card:nth-child\(2\):hover[^}]*rotate\(/s);
    expect(styles).toMatch(/\.immune-level-two-answer-card:nth-child\(3\):hover[^}]*rotate\(/s);
    expect(styles).toMatch(/transition:[^;}]*cubic-bezier\(\.16,\s*1,\s*\.3,\s*1\)/);
    expect(styles).toMatch(/\.immune-level-two-answer-card:active[^}]*{[^}]*scale\(/s);
    expect(styles).toMatch(/\.immune-level-two-quiz\s*{[^}]*animation:\s*immune-level-two-quiz-enter 350ms/s);
    const shake = styles.match(/@keyframes immune-level-two-shake-three[^\n]*/)?.[0] ?? "";
    expect((shake.match(/translateX\(-\d+px\)/g) ?? [])).toHaveLength(3);
    expect((shake.match(/translateX\(\d+px\)/g) ?? [])).toHaveLength(3);
    expect(styles).toMatch(/@media \(max-width:\s*720px\)[\s\S]*\.immune-level-two-answer-row[^{]*{[^}]*flex-direction:\s*row/s);
    const reducedMotionStart = styles.indexOf(
      "@media (prefers-reduced-motion: reduce)",
      styles.indexOf("@keyframes immune-level-two-shake-three"),
    );
    const reducedMotion = styles.slice(reducedMotionStart, styles.indexOf("@keyframes", reducedMotionStart));
    expect(reducedMotion).toMatch(/\.immune-level-two-answer-card[\s\S]*transform:\s*none/);
    expect(reducedMotion).toMatch(/\.immune-level-two-quiz\.immune-is-incorrect \.immune-level-two-answer-row\s*{\s*animation:\s*none/);
    expect(reducedMotion).toMatch(/\.immune-level-two-quiz\.immune-is-incorrect::after\s*{[^}]*animation:\s*immune-level-two-soft-flash/);
    const softFlash = styles.match(/@keyframes immune-level-two-soft-flash[^\n]*/)?.[0] ?? "";
    expect(softFlash).toMatch(/opacity:\s*\.42/);
  });

  it("exposes one documented width and height control shared by all three cards", () => {
    const rowRule = styles.match(/\.immune-level-two-answer-row\s*\{[^}]*\}/s)?.[0] ?? "";
    const cardRule = styles.match(/\.immune-level-two-answer-card\s*\{[^}]*\}/s)?.[0] ?? "";
    const mobileStart = styles.indexOf(
      "@media (max-width: 720px)",
      styles.indexOf("@keyframes immune-level-two-shake-three"),
    );
    const mobileRules = styles.slice(mobileStart, styles.indexOf("@media", mobileStart + 1));

    expect(rowRule).toMatch(/--immune-answer-card-width:\s*[^;]+;\s*\/\*[^*]*宽[^*]*微调[^*]*\*\//);
    expect(rowRule).toMatch(/--immune-answer-card-height:\s*[^;]+;\s*\/\*[^*]*高[^*]*微调[^*]*\*\//);
    expect(cardRule).toMatch(/width:\s*min\(var\(--immune-answer-card-width\),\s*100%\)/);
    expect(cardRule).toMatch(/height:\s*var\(--immune-answer-card-height\)/);
    expect(mobileRules).toMatch(/\.immune-level-two-answer-card\s*\{[^}]*width:\s*min\(var\(--immune-answer-card-width\),\s*100%\)/s);
    expect(mobileRules).not.toMatch(/\.immune-level-two-answer-card\s*\{[^}]*min-height:/s);
  });
});
