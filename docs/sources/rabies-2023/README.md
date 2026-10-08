# 狂犬病官方规范来源

原件为中国疾控技术文件栏目收录的《狂犬病暴露预防处置工作规范（2023年版）》，文号国疾控综传防发〔2023〕14号，国家疾控局综合司与国家卫生健康委员会办公厅于 2023-09-13 联合印发。

- [中国疾控原始 PDF](https://www.chinacdc.cn/jkyj/crb2/yl/kqb/jswj_kqb/202409/P020240906525421817465.pdf)
- [国家疾控局通知与正文](https://www.ndcpa.gov.cn/jbkzzx/c100012/common/content/content_1706568784078565376.html)
- `official.pdf`：下载原件，共 12 页，包含通知、规范和知情同意书附件。
- `source_record.json`：发行机构、文件日期、来源 URL 与 PDF/Markdown SHA256。
- RAG 转存文件：`RAG/国家政策与免疫规划/狂犬病暴露预防处置工作规范（2023年版）.md`。

原 PDF 没有可直接提取的文字层。RAG 使用与原件同版的官方网页正文，按五章三十条转存为 Markdown；不加入附件表单，不补写医学解释，不将扫描 PDF 重复入索引。正文通过现有 structure-aware Markdown loader 与 chunker 进入候选索引，来源指向中国疾控原件，条款保存在 section provenance 中，page 为 null，不虚构 PDF 页码。

语料准入状态为 `auto_classified`，不冒称完成医学人工审核。新增来源不能追溯为 SCI-013/SCI-020 原回答当时已引用的证据，也不能把“暴露后接种无禁忌症”扩展成已经核实所有胎儿风险结论。
