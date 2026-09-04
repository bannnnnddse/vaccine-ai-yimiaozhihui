# 功能级一键复现

本项目交付的是功能级复现：第三方以受治理语料、固定上游模型 revision 和既有 Hybrid RAG V2 管线，恢复可运行的检索环境。它不承诺生成与任一生产索引字节相同的版本，也不分发生产 active RAG index 或 Graph snapshot。

## 使用方式

```powershell
git clone <repository-url> vaccine-ai
cd vaccine-ai
copy backend\.env.example backend\.env
# 填写 DASHSCOPE_API_KEY
python scripts\bootstrap_assets.py
docker compose up -d --build
curl http://localhost/api/v1/health
```

`bootstrap_assets.py` 固定下载下列官方 Hugging Face revision，且下载后必须以 `local_files_only=True` 实际加载；目录存在但缺少权重时会失败并重试，不会给出假阳性。

| 角色 | 官方模型 | 固定 revision |
| --- | --- | --- |
| Dense embedding | `BAAI/bge-small-zh-v1.5` | `7999e1d3359715c523056ef9478215996d62a620` |
| Cross-encoder reranker | `BAAI/bge-reranker-base` | `2cfc18c9415c912f9d8155881c133215df768a70` |

随后脚本以 `scripts/prepare_rag_artifacts.py` 从仓库 `RAG/` 生成本机 PDF page-block artifacts，并调用与 `python -m app.rag.cli build-v2` 共用的 V2 builder，生成和激活新的 Hybrid RAG index。Graph 不由 bootstrap 重建。

## 已确认的验证范围

基线 commit：`6f60098449afcf83da1d13604f63bdbf5ca8b646`。

- 隔离云端 clean-clone 已完成模型官方固定 revision 恢复、PDF artifacts 准备、全量 Hybrid RAG V2 构建与激活、Docker build/start、health 检查及三条 retrieval smoke。
- V2 corpus 由 121 个 PDF artifacts 与 11 份 Markdown 来源组成，共 132 份准入文档、17,167 个 chunks；活动版本采用 builder 生成的时间戳式 index version。
- 构建产物为本机新建的 Hybrid RAG V2；模型来自官方固定 revision，索引由 clean-clone 的仓库 `RAG/` 语料生成，未复制生产 active index、Graph snapshot 或 model cache。
- `verify_assets.py`、backend/frontend 容器启动、embedding/reranker/活动索引加载均通过；三条固定检索问题的 Top-4 均返回证据结果。

项目已在隔离 clean-clone 云端环境完成核心 Hybrid RAG 的端到端功能级复现验证。第三方无需获得团队生产 active index，可通过固定模型版本、仓库语料和 bootstrap 在本地恢复可运行的 Hybrid RAG 环境。

全量 embedding 是 CPU 密集型步骤；实际耗时受网络、CPU、磁盘和模型下载影响。任何实测耗时仅代表对应验证机器，**不构成部署耗时保证**。

## 125 份 PDF 与 121 个 parsed artifacts

121 是 V2 PDF 准入后的预期数量，不是四份解析失败。其余四份均按照治理规则排除：

| 类型 | 数量 | 原因 |
| --- | ---: | --- |
| 不完整试读预览 | 1 | `《全民健康十万个为什么：免疫与接种》.pdf` 为低文本 OCR 试读，authority=0；按最低 authority 准入规则排除。 |
| 精确重复 | 3 | `预防接种工作规范 .pdf`、2026 年免疫程序重复收录文件、`针对疫苗错误信息的沟通干预措施.pdf` 分别与 corpus manifest 中的规范版本/主收录文件具有 `duplicate_of` 关系，按去重规则排除。 |

这些都是预期的语料治理行为，不影响 active corpus 的预期知识覆盖：试读预览不作为正式证据，三份重复内容均由其主收录文档覆盖。

## `verify_assets.py` 的检查口径

验证脚本检查：

- 两个 manifest 指定 revision 的目录存在，且 embedding/reranker 均能离线真实加载；
- `active.json` 存在，活动版本目录含 `chunks.jsonl`、`dense_records.jsonl`、`dense_store.json`、`vectors.npy` 和 `manifest.json`；
- 必要 V2 index 目录结构存在。

隔离云端验收中，以上检查均通过；活动 index 与 corpus manifest 兼容，必要目录结构完整。

## Docker、检索与 Graph fallback

隔离云端 clean-clone 的 Docker backend/frontend、health、embedding、reranker、活动 Hybrid RAG 及三条 retrieval smoke 均通过。smoke 问题为“疫苗接种有什么作用？”、“什么是群体免疫？”和“为什么需要完成全程接种？”，每条均获得非空 Top-4 证据结果。

GraphRAG 是可选增强。clean clone 不携带生产 graph snapshot；当图不存在、损坏或与活动 index 不匹配时，公共图 API 不提供图数据，问答沿既有机制安全降级为 Hybrid RAG / Vector-only。核心 Hybrid RAG 不依赖 Graph 重建。

## 资产隔离

bootstrap 仅从官方源下载固定模型 revision，并从 clean-clone 中的 `RAG/` 语料本地构建 index。它不复制或打包生产 `backend/rag_index/active.json`、版本目录、`backend/runtime/graph/` snapshot 或模型 cache。生产资产之所以不公开，是因为它们包含完整 chunk/provenance 正文、文献元数据和生产历史。
