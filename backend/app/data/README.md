# 图解证据绑定边界

旧 `organize()`、空白名单及匹配逻辑已删除。正式图解通过 `ScienceImageEvidenceService` 独立调用现有本地 RAG，将每个科学表述和因果步骤绑定到真实切片、逐字摘录与索引版本；来源元数据由后端生成。没有有效依据、绑定缺失、数字单位不对应或支持检查失败时停止生成。

生成与 critic 使用同一来源契约；重试重新检索，编辑不得扩展原科学内容。API、图像审计文件和前端会话保存来源记录。来源绑定状态为 `sources_bound`，`medical_review_required` 始终为 true，不使用“医学事实已核验”标记。PubMed 图解检索和真实生图科学性评测本轮未实施。

详见 [实现与验证记录](../../../docs/science-image-grounding-2026-10-08.md)。
