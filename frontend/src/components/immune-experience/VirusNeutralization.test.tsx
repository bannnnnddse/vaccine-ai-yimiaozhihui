import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import {
  VirusNeutralization,
  createVirusBindingParticles,
  createVirusNeutralizationParticles,
} from "./VirusNeutralization";

describe("VirusNeutralization", () => {
  it("creates sixty deterministic antibodies balanced across four viruses", () => {
    const particles = createVirusNeutralizationParticles();

    expect(particles).toHaveLength(60);
    expect(Array.from({ length: 4 }, (_, virusIndex) => (
      particles.filter((particle) => particle.virusIndex === virusIndex).length
    ))).toEqual([15, 15, 15, 15]);
    expect(createVirusNeutralizationParticles()).toEqual(particles);
  });

  it("creates nine focus antibodies with two or three assigned to every virus", () => {
    const particles = createVirusBindingParticles();

    expect(particles).toHaveLength(9);
    expect(Array.from({ length: 4 }, (_, virusIndex) => (
      particles.filter((particle) => particle.virusIndex === virusIndex).length
    ))).toEqual([3, 2, 2, 2]);
    expect(createVirusBindingParticles()).toEqual(particles);
  });

  it("keeps all antibodies drifting before viruses enter", () => {
    const markup = renderToStaticMarkup(<VirusNeutralization phase="antibody-drift" />);

    expect(markup.match(/data-antibody-particle=/g)).toHaveLength(60);
    expect(markup).not.toContain("data-binding-antibody");
    expect(markup).not.toContain("data-neutralization-virus");
    expect(markup).toContain("is-drifting");
  });

  it("renders four staggered viruses during entry", () => {
    const markup = renderToStaticMarkup(<VirusNeutralization phase="virus-entry" />);

    expect(markup.match(/data-neutralization-virus=/g)).toHaveLength(4);
    expect(markup.match(/data-withdrawing-antibody=/g)).toHaveLength(60);
    expect(markup.match(/data-binding-antibody=/g)).toHaveLength(9);
    expect(markup).toContain("is-withdrawing");
    expect(markup).toContain("is-emerging");
    expect(markup).toContain("is-entering");
  });

  it("binds every antibody to a virus in the final state", () => {
    const markup = renderToStaticMarkup(<VirusNeutralization phase="neutralized" />);

    expect(markup.match(/data-neutralization-virus=/g)).toHaveLength(4);
    expect(markup.match(/data-binding-antibody=/g)).toHaveLength(9);
    expect(markup.match(/data-bound-virus=/g)).toHaveLength(9);
    expect(markup).toContain("is-bound");
  });

  it("defines transform-only motion for drift, entry, binding and the final clusters", () => {
    const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");

    expect(styles).toContain("@keyframes immune-antibody-persistent-drift");
    expect(styles).toContain("@keyframes immune-antibody-withdraw");
    expect(styles).toContain("@keyframes immune-focus-antibody-emerge");
    expect(styles).toContain("@keyframes immune-virus-enter");
    expect(styles).toContain("@keyframes immune-antibody-bind");
    expect(styles).toContain("@keyframes immune-neutralized-cluster-float");
    expect(styles).toMatch(/prefers-reduced-motion[\s\S]*immune-virus-neutralization/);
  });
});
