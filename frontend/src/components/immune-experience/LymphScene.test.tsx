import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { createLevelThreeCells } from "./levelThreeState";
import { LymphScene } from "./LymphScene";

function renderPhase(
  phase: Parameters<typeof LymphScene>[0]["phase"],
  onInterludeCaptionComplete?: () => void,
  exitingActivationCaption?: Parameters<typeof LymphScene>[0]["exitingActivationCaption"],
) {
  return renderToStaticMarkup(
    <LymphScene
      cells={createLevelThreeCells(() => 0.4)}
      showCells
      openingCaption={null}
      openingStage="ready"
      phase={phase}
      selectedCellId={null}
      revealedCellIds={["b-cell", "helper-t-cell"]}
      speech={null}
      speechTone="info"
      onSelectCell={() => undefined}
      onInterludeCaptionComplete={onInterludeCaptionComplete}
      exitingActivationCaption={exitingActivationCaption}
    />,
  );
}

describe("LymphScene activation handoff", () => {
  it("removes all exploration cells before rendering the central activation sequence", () => {
    const markup = renderToStaticMarkup(
      <LymphScene
        cells={createLevelThreeCells(() => 0.4)}
        showCells
        openingCaption={null}
        openingStage="ready"
        phase="focus-b-cell"
        selectedCellId={null}
        revealedCellIds={["b-cell", "helper-t-cell"]}
        speech={null}
        speechTone="info"
        onSelectCell={() => undefined}
      />,
    );

    expect(markup).not.toContain("data-cell-id=");
    expect(markup).toContain("data-helper-t-focus");
  });

  it("keeps exploration cells removed through the final neutralized state", () => {
    const markup = renderToStaticMarkup(
      <LymphScene
        cells={createLevelThreeCells(() => 0.4)}
        showCells
        openingCaption={null}
        openingStage="ready"
        phase="neutralized"
        selectedCellId={null}
        revealedCellIds={["b-cell", "helper-t-cell"]}
        speech={null}
        speechTone="info"
        onSelectCell={() => undefined}
      />,
    );

    expect(markup).not.toContain("data-cell-id=");
    expect(markup.match(/data-neutralization-virus=/g)).toHaveLength(4);
  });

  it("shows both activation captions in the shared translucent bubble", () => {
    const contactMarkup = renderPhase("t-cell-contact");
    const animationMarkup = renderPhase("antigen-presentation");
    const holdMarkup = renderPhase("antigen-presentation-hold");

    expect(contactMarkup).toContain("immune-level-three-activation-caption is-contact");
    expect(contactMarkup).toContain("树突状细胞会将抗原标志物呈递给辅助性T细胞，\n并使其活化");
    expect(animationMarkup).toContain("immune-level-three-activation-caption");
    expect(animationMarkup).toContain("is-helper-to-b");
    expect(animationMarkup).not.toContain("text-type");
    expect(holdMarkup).toContain("immune-level-three-activation-caption");
    expect(holdMarkup).toContain("辅助性T细胞经树突状细胞激活后，迁移至B细胞区域为其提供第二活化信号");
    expect(renderPhase("antigen-presentation-hold", undefined, "helper-to-b")).toContain("is-exiting");
  });

  it("passes the helper-T contact hold into the nested activation sequence", () => {
    const markup = renderPhase("t-cell-contact-hold");

    expect(markup).toContain("immune-b-cell-activation is-t-cell-contact-hold");
  });

  it("passes the antigen-presentation hold into the nested activation sequence", () => {
    const markup = renderPhase("antigen-presentation-hold");

    expect(markup).toContain("immune-b-cell-activation is-antigen-presentation-hold");
  });

  it("routes the outcome scenes and both interlude captions", () => {
    const markup = renderPhase("outcome-scenes");
    expect(markup).toContain("被吞噬清除");
    expect(markup.match(/data-outcome-scene=/g)).toHaveLength(3);
    expect(renderPhase("however-caption")).toContain("分化后的记忆B细胞会留在体内长期驻守");
    expect(renderPhase("rechallenge-caption")).toContain("当真正的病毒再次入侵时……");
  });

  it("types both interlude captions", () => {
    expect(renderPhase("however-caption")).toContain("text-type");
    expect(renderPhase("rechallenge-caption")).toContain("text-type");
  });

  it("wires both completed interlude captions to the hold callback", () => {
    const onComplete = () => undefined;

    expect(renderPhase("however-caption", onComplete)).toContain("text-type");
    expect(renderPhase("rechallenge-caption", onComplete)).toContain("text-type");
  });

  it("routes memory recall into the iris blackout", () => {
    expect(renderPhase("memory-recall").match(/data-recall-virus=/g)).toHaveLength(3);
    expect(renderPhase("iris-focus")).toContain("is-iris-focus");
    expect(renderPhase("blackout")).toContain("is-blackout");
  });

  it("never restores exploration cells during the finale", () => {
    const finalePhases = [
      "outcome-transition",
      "outcome-scenes",
      "outcome-exit",
      "interlude-pause",
      "however-caption",
      "rechallenge-caption",
      "memory-recall",
      "memory-awakening",
      "memory-antibody-storm",
      "iris-focus",
      "iris-hold",
      "iris-close",
      "blackout",
    ] as const;

    for (const phase of finalePhases) {
      expect(renderPhase(phase)).not.toContain("data-cell-id=");
    }
  });
});
