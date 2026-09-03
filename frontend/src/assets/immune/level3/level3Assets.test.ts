import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { level3Assets } from "./level3Assets";

describe("level3Assets", () => {
  it("registers the mirrored RGBA B-cell mascot on its original canvas", () => {
    expect(level3Assets.bCell).toContain("b-cell.png");
    expect(level3Assets.bCellPatrol).toContain("b-cell-patrol.png");

    for (const path of ["./b-cell.png", "./b-cell-patrol.png"]) {
      const bytes = readFileSync(new URL(path, import.meta.url));
      expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
      expect(bytes.readUInt32BE(16)).toBe(1045);
      expect(bytes.readUInt32BE(20)).toBe(1564);
      expect(bytes.readUInt8(25)).toBe(6);
    }
  });

  it("uses the requested RGBA virus asset for all patrol viruses", () => {
    expect(level3Assets.patrolVirus).toContain("patrol-virus-transparent.png");

    const bytes = readFileSync(new URL("./patrol-virus-transparent.png", import.meta.url));
    expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
    expect(bytes.readUInt8(25)).toBe(6);
  });

  it("registers the requested helper T and antigen-presenting dendritic PNGs", () => {
    expect(level3Assets.helperTCell).toContain("helper-t-cell.png");
    expect(level3Assets.helperTCellLabel).toContain("helper-t-cell-label.png");
    expect(level3Assets.antigenPresentingCell).toContain("antigen-presenting-cell.png");

    for (const path of ["./helper-t-cell.png", "./helper-t-cell-label.png", "./antigen-presenting-cell.png"]) {
      const bytes = readFileSync(new URL(path, import.meta.url));
      expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
      expect(bytes.readUInt8(25)).toBe(6);
    }

    const labelBytes = readFileSync(new URL("./helper-t-cell-label.png", import.meta.url));
    expect(labelBytes.readUInt32BE(16)).toBe(847);
    expect(labelBytes.readUInt32BE(20)).toBe(187);
  });

  it("registers RGBA assets for the memory response scene", () => {
    expect(level3Assets).toHaveProperty("virusParticle");
    expect(level3Assets).toHaveProperty("sleepingMemoryBCell");
    expect(level3Assets).toHaveProperty("angryMemoryBCell");
    expect(level3Assets).toHaveProperty("memoryBCell");

    for (const path of [
      "./virus-particle.png",
      "./sleeping-memory-b-cell.png",
      "./angry-memory-b-cell.png",
    ]) {
      expect(readFileSync(new URL(path, import.meta.url)).readUInt8(25)).toBe(6);
    }
  });

  it("registers the four generated RGBA outcome sprites", () => {
    expect(level3Assets.outcomeMacrophage).toContain("macrophage-side-open-mouth.png");
    expect(level3Assets.outcomeVirusRuptured).toContain("virus-ruptured.png");
    expect(level3Assets.outcomeVirusNauseated).toContain("virus-nauseated.png");
    expect(level3Assets.outcomeVirusDead).toContain("virus-dead.png");

    for (const path of [
      "./outcomes/macrophage-side-open-mouth.png",
      "./outcomes/virus-ruptured.png",
      "./outcomes/virus-nauseated.png",
      "./outcomes/virus-dead.png",
    ]) {
      const bytes = readFileSync(new URL(path, import.meta.url));
      expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
      expect(bytes.readUInt8(25)).toBe(6);
    }
  });
});
