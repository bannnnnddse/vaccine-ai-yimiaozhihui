# 图解事实白名单的边界

`verified_visual_facts.json` 当前为 `[]`，没有经人工审核的定量事实。空列表是显式禁用已核验数字的状态，不是已完成的视觉事实库。

旧 `ScienceImageOrganizer.organize()` 仅在 label、value、unit、scope、source 与白名单匹配时标记 `verified`；未匹配数字保持 `candidate`，`is_renderable=false`。正式 image jobs 则调用 `refine()`，没有经过该白名单，也没有独立的 RAG/PubMed 事实检索。**只填充此文件不会修复正式图解的证据核验。** critic 是视觉风险审核，不是医学证据审查。

补充前先由医学审核人确认原文、人群、疫苗类型、年份、数值和单位，记录精确页码/条款、来源链接、审核人及日期。正式条目仅含 `label`、数值 `value`、`unit`、`scope`、`source`；审核记录另存，不能添加 schema 不接受的字段。不要将示例数字、模型记忆或未经审核的外部资料标记为 verified。

要为正式任务提供事实保障，后续需将本轮证据与每项科学主张绑定，核验后再交给生成和 critic，并补充不支持/错疫苗/错人群的离线测试。该改造尚未完成。
