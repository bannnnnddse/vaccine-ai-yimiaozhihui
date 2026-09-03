import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  createImageParticles,
  ImageGenerationFrame,
  PARTICLE_COLUMNS,
  PARTICLE_ROWS,
} from "./ImageGenerationFrame";

describe("ImageGenerationFrame", () => {
  it("creates a 9 by 6 radial particle field with deterministic phases", () => {
    const particles = createImageParticles();
    const center = particles.find((particle) => particle.row === 2 && particle.column === 4)!;
    const corner = particles.find((particle) => particle.row === 0 && particle.column === 0)!;

    expect(PARTICLE_COLUMNS).toBe(9);
    expect(PARTICLE_ROWS).toBe(6);
    expect(particles).toHaveLength(54);
    expect(new Set(particles.map(({ row, column }) => `${row}:${column}`))).toHaveLength(54);
    expect(center.phase).toBeLessThan(corner.phase);
    expect(center.restScale).toBeGreaterThan(corner.restScale);
    expect(center.restOpacity).toBeGreaterThan(corner.restOpacity);
  });

  it("renders one black status line over an aria-hidden particle field", () => {
    const markup = renderToStaticMarkup(
      <ImageGenerationFrame
        title="正在构思"
        alt="水痘发病机制"
      />,
    );

    expect(markup.match(/class="particle-grid__particle"/g)).toHaveLength(54);
    expect(markup).toContain('class="particle-grid" aria-hidden="true"');
    expect(markup).toContain('class="generation-title">正在构思');
    expect(markup).not.toContain("generation-description");
    expect(markup).toContain("--particle-delay:-");
  });

  it("renders a hidden semantic result image inside the same frame", () => {
    const markup = renderToStaticMarkup(
      <ImageGenerationFrame
        title="正在构思"
        imageUrl="/api/v1/generated-images/job-1.png"
        alt="水痘发病机制"
      />,
    );

    expect(markup).toContain('src="/api/v1/generated-images/job-1.png"');
    expect(markup).toContain('alt="水痘发病机制"');
    expect(markup).toContain('class="image-generation-frame__image"');
  });
});
