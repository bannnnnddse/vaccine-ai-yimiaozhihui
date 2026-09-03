// @ts-expect-error Node types are intentionally not part of the browser application.
import { createHash } from "node:crypto";
// @ts-expect-error Node types are intentionally not part of the browser application.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { immuneAssets } from "./immuneAssets";

const replacementVirusUrl = new URL("./virus.png", import.meta.url);
const antigenDendriticUrl = new URL("./antigen-dendritic-cell.png", import.meta.url);

describe("replacement virus asset", () => {
  it("keeps the shared non-maze virus states on one stable transparent PNG", () => {
    expect(immuneAssets.virusNeutral).toBe(immuneAssets.virusNervous);
    expect(immuneAssets.virusNeutral).toContain("virus.png");
  });

  it("uses dedicated assets for maze virus and dendritic cell", () => {
    expect(immuneAssets.virusExploring).toContain("maze-virus.png");
    expect(immuneAssets.mazeDendriticCell).toContain("maze-dendritic-cell.png");
  });

  it("keeps the antigen-presentation dendritic asset as a transparent PNG", () => {
    const bytes = readFileSync(antigenDendriticUrl);

    expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
    expect(bytes[25]).toBe(6);
  });

  it("keeps the approved source bytes unchanged", () => {
    const bytes = readFileSync(replacementVirusUrl);
    expect(createHash("sha256").update(bytes).digest("hex").toUpperCase()).toBe(
      "D77EE6C70A91830972A662054CCBD8C16E34822D00831D832E804F4E08222793",
    );
    expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
    expect(bytes.readUInt32BE(16)).toBe(1024);
    expect(bytes.readUInt32BE(20)).toBe(1024);
    expect(bytes[25]).toBe(6);
  });
});
