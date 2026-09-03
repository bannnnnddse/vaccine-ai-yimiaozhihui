import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AdminEntryLink } from "./AdminEntryLink";

describe("AdminEntryLink", () => {
  it("links the public workspace to the isolated admin route", () => {
    const html = renderToStaticMarkup(<AdminEntryLink />);

    expect(html).toContain('href="/admin"');
    expect(html).toContain("审核入口");
    expect(html).not.toContain("Evidence desk");
    expect(html).not.toContain(">KG<");
    expect(html).toContain("进入 KnowledgeGap 管理审核后台");
  });
});
