import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AdminHomeLink } from "./AdminHomeLink";

describe("AdminHomeLink", () => {
  it("returns from the admin area to the public main page", () => {
    const html = renderToStaticMarkup(<AdminHomeLink />);

    expect(html).toContain('href="/"');
    expect(html).toContain("返回主页面");
  });
});
