# 图解事实核验边界

正式 image jobs 调用 `ScienceImageOrganizer.refine()`。旧 `organize()`、空 `verified_visual_facts.json`、白名单加载及匹配逻辑已删除，详见 [清理记录](../../../docs/science-image-legacy-cleanup-2026-10-08.md)。

正式任务目前没有独立 RAG/PubMed 事实检索。brief 中的科学表述由模型整理，critic 负责视觉和潜在科学表达风险审查；二者不能证明医学事实已核验，医学内容仍需人工复核。

后续需将当轮可追溯证据与每项科学主张绑定，核对疫苗、人群、适用条件、数值及单位，证据不足时限制生成内容或转人工审核；再将核验结果传给生成和审查，并补充无来源、错疫苗、错人群等离线测试。该改造尚未完成。
