# 狂犬病规范语料接入（2026-10-08）

新增中国疾控官网收录的《狂犬病暴露预防处置工作规范（2023年版）》，原件落款为国家疾控局综合司、国家卫生健康委员会办公厅，文号国疾控综传防发〔2023〕14号，文件日期 2023-09-13。

[中国疾控原件](https://www.chinacdc.cn/jkyj/crb2/yl/kqb/jswj_kqb/202409/P020240906525421817465.pdf) 与 [国家疾控局同版正文](https://www.ndcpa.gov.cn/jbkzzx/c100012/common/content/content_1706568784078565376.html) 共同构成来源核对依据。原 PDF 为 12 页扫描件，没有直接可提取的文字层，因此原件保存在 `docs/sources/rabies-2023/official.pdf`，RAG 采用同版官方网页正文转存 Markdown；五章三十条完整保留，不补写医学结论，不导入附件表单。

## 接入范围

- RAG 新增 `国家政策与免疫规划/狂犬病暴露预防处置工作规范（2023年版）.md`。
- 清单从 140 增至 141 条（125 PDF、12 MD、4 DOCX），原 140 条清单记录保留；新增记录包含联合发行机构、日期、版本、authority=4、guideline 与 high 元数据置信度。
- 原件与转存文件的 SHA256 见 `docs/sources/rabies-2023/source_record.json`。
- 使用已有 `load_structured_markdown`、`split_structured_document`、`build_candidate_index` 与 `RagService.for_index_version`；没有新增运行时 parser、chunker、embedder 或向量写入器。
- 正文形成 31 个条款/介绍切片，来源 URL 指向中国疾控原件，section 保留条款；Markdown 来源 page 为 null，不虚构 PDF 页码。
- 准入状态为 `auto_classified`，不是医学人工审核。旧抽检原始输出和人工评分不因此变为已核验。

## 验证范围

新增 3 项离线回归检查官方来源身份/哈希、五章三十条完整性、暴露前后范围及条款 provenance。开发项目全量后端 500 项通过，lint 与源码预检通过。全量测试中修正了一处已有客户端数量断言：现在验证所有共享客户端关闭环境代理继承，不再固定为两个；该测试修正不涉及 PubMed 业务改动。

另设独立 8 条候选检索 smoke（6 个狂犬病条款正例、2 个其他疫苗负例），读取既有本地模型，禁用网络下载，不调用 Qwen/Wan 或图谱抽取。用例和复核脚本为：

```powershell
cd backend
.\.venv\Scripts\python.exe ..\scripts\evaluate_rabies_retrieval.py --index-version <candidate-version> --output runtime\rabies-retrieval-report.json
```

实际验证结果：**8/8 通过**，六个正例均在 Top-4 召回对应条款，两个其他疫苗负例的 Top-4 未混入该规范；全部使用 Hybrid V2，无回退。候选 `rag-v2-20261008T055626803051Z-66375f88` 包含 133 份有效文档、17,198 个切片，结构校验与绑定该版本的检索 gate 通过。逐例条款、chunk ID、来源和耗时保存在 [retrieval_report.json](evaluation/rabies_2023/retrieval_report.json)。

检索结果不等于最终回答科学正确率，也不能替代独立的医学人工审核。该 smoke 围绕此次新增资料构造，不是独立泛化 benchmark；原 1000 条冻结评测、SCI 原始回答与人工 CSV 没有改写。

## 发布边界

本次加入的是受治理源文件与验证记录。模型缓存、候选向量目录、active pointer 和 Graph snapshot 不同步到展示 Git 仓库。生产活动版本未改，未构建新图谱；上线须在部署环境完成候选验证和同版发布。不得将本次资料补齐描述为旧回答当时已取得这些引用。
