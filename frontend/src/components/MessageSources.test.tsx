import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MessageSources } from "./MessageSources";

describe("MessageSources", () => {
  it("renders file, one-based page and expandable excerpt", () => {
    const html = renderToStaticMarkup(<MessageSources sources={[{
      fileName: "儿童免疫规划指南.pdf",
      page: 12,
      content: "相关文本片段",
    }]} />);

    expect(html).toContain("参考来源 1");
    expect(html).toContain("儿童免疫规划指南.pdf");
    expect(html).toContain("第12页");
    expect(html).toContain("相关文本片段");
    expect(html).toContain("<details");
    expect(html).toContain("<summary");
  });

  it("renders nothing for an empty source list", () => {
    expect(renderToStaticMarkup(<MessageSources sources={[]} />)).toBe("");
  });

  it("renders merged page numbers as one source", () => {
    const html = renderToStaticMarkup(<MessageSources sources={[{
      fileName: "接种规范.pdf",
      page: 3,
      pages: [3, 7],
      content: "两个页面的合并片段",
    }]} />);

    expect(html).toContain("参考来源 1");
    expect(html).toContain("第3、7页");
  });

  it("renders an official web source without a fabricated page number", () => {
    const html = renderToStaticMarkup(<MessageSources sources={[{
      fileName: "水痘疫苗国家疾控权威接种规范.md",
      page: null,
      content: "相关文本片段",
      sourceType: "web",
      sourceTitle: "疫苗免疫预防（水痘）",
      sourceUrl: "https://www.chinacdc.cn/example",
      section: "接种建议",
    }]} />);

    expect(html).toContain("疫苗免疫预防（水痘）");
    expect(html).toContain("官方网页");
    expect(html).toContain("接种建议");
    expect(html).toContain("查看官网原文");
    expect(html).not.toContain("第null页");
  });

  it("renders a PubMed source with year and article link", () => {
    const html = renderToStaticMarkup(<MessageSources sources={[{
      fileName: "HPV vaccine safety study",
      page: null,
      content: "摘要片段。",
      sourceType: "pubmed",
      sourceTitle: "HPV vaccine safety study",
      sourceUrl: "https://pubmed.ncbi.nlm.nih.gov/12345678/",
      pmid: "12345678",
      journal: "Vaccine",
      year: 2025,
    }]} />);

    expect(html).toContain("PubMed · 2025");
    expect(html).toContain("查看 PubMed");
    expect(html).toContain("HPV vaccine safety study");
  });

  it("labels a published curated source as manually reviewed knowledge", () => {
    const html = renderToStaticMarkup(<MessageSources sources={[{
      fileName: "gap123.md",
      page: null,
      content: "经人工确认的知识主张。",
      sourceType: "curated",
      sourceTitle: "HPV 疫苗保护机制",
      sourceUrl: "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    }]} />);

    expect(html).toContain("人工审核知识");
    expect(html).toContain("查看主要证据");
  });
});
