# 高风险疫苗问答·最终回答科学正确性人工抽检（Scientific Correctness Audit）

## 1. 为什么进行这个测试

本仓库已有一项检索层评测（1081 条问题，Top-4 正确证据检索成功率 88.62%，见 [../evaluation.md](../evaluation.md)）。检索召回率高不等于最终回答正确——正确证据进入上下文之后，语言模型仍可能在组织回答时引入事实错误、过度承诺或越界医疗建议。

本目录记录一个**小规模最终回答科学正确性人工抽检**：固定 20 条高风险疫苗科普问题，通过**生产问答链路**真实运行，将系统原始输出冻结，由人工按统一标准审核四项指标（科学正确性、引用支持、严重医学错误、安全边界）。

## 2. 文件说明

| 文件 | 说明 |
| --- | --- |
| `README.md` | 本文件：目的、运行方式、配置快照 |
| `evaluation_cases.jsonl` | 正式评测的 20 条问题（SCI-001 ~ SCI-020），含 gold_points / critical_errors / reference_scope，评测前固定 |
| `raw_outputs.jsonl` | 系统对 20 条问题的**原始输出**（逐条一次运行，不重采样），含引用、延迟、错误与运行 commit |
| `human_review.csv` | 人工审核表，判定字段（scientific_correct / citation_supported / critical_error / safety_boundary / reviewer / notes）必须由**人工填写** |
| `model_assisted_review.csv` | （可选）模型辅助初筛结果，**仅用于辅助人工审核，不计入正式人工评测结果** |
| `review_guideline.md` | 四项核心指标与判定细则 |
| `summary.json` | 由脚本从 human_review.csv 生成；人工未完成时状态为 `pending_human_review`，不产生任何正确率数字 |
| `report.md` | 面向评委的短报告，人工审核完成前不显示任何正确率 |

## 3. 如何重新运行 20 条问题

前置条件：

1. `backend/.env` 已配置（参照 `backend/.env.example`，填入 `DASHSCOPE_API_KEY` 等）。**该文件被 .gitignore 排除，不得提交。**
2. 已构建的 RAG 索引位于 `backend/rag_index/`（含 `active.json`），模型缓存位于 `backend/model_cache/`——这些运行时资产不入库，按根目录 DEPLOYMENT.md 的私密通道传输。
3. 已安装后端依赖：`pip install -e "backend[dev]"`（或使用开发虚拟环境）。

运行：

```bash
cd backend
python ../scripts/evaluate_scientific_correctness.py --run
```

脚本通过 `fastapi.testclient` 调用与线上完全相同的 `POST /api/v1/chat` 入口（lifespan 内的 RagService / QwenService / EvidenceAssessment / PubMed 链路），逐条运行 SCI-001 ~ SCI-020，把**模型原始输出**追加写入 `raw_outputs.jsonl`。每条记录包含 commit、时间戳与延迟。

规则：**每题只保留第一次有效运行结果**；若因网络/API 基础设施故障完全未形成答案，修复后可重跑该题，但须在本 README 记录"基础设施失败重试"。禁止因回答内容不满意而重采样。

## 4. 如何填写 human_review.csv

1. 打开 `human_review.csv`，对照 `raw_outputs.jsonl` 的原始回答与 `review_guideline.md` 的判定细则。
2. 仅由人工填写四列判定值（0/1）：`scientific_correct`、`citation_supported`、`critical_error`、`safety_boundary`，并在 `reviewer` 填写审核人。
3. 不要参考或抄写 `model_assisted_review.csv` 的数值来填写正式表。
4. `notes` 可记录判定理由；`answer_excerpt` 辅助列仅为方便定位。

## 5. 如何重新生成 summary.json 与 report.md

```bash
cd backend
python ../scripts/evaluate_scientific_correctness.py --summarize
```

- 20 条全部有人工判定后：生成 `status: "completed"` 的 `summary.json`，并刷新 `report.md` 的结果小节。
- 仍有空白时：`summary.json` 保持 `status: "pending_human_review"`，所有指标为 `null`；空白**不会**被当作通过，也不会用 AI 初筛填充。

## 6. 当前评测配置快照

- 分支：`main`
- 评测设计与用例固定 commit：`435a3d2c` 之后的文档/样例提交序列（运行时精确 commit 由脚本写入每条 `raw_outputs.jsonl` 的 `commit` 字段）
- 测试日期：2026-09-03
- 问答主模型：`qwen3.8-flash`（DashScope，OpenAI 兼容接口）
- 轻量路由模型：`qwen3.8-flash`
- Embedding：`BAAI/bge-small-zh-v1.5`（本地 CPU）
- Reranker：`BAAI/bge-reranker-base`（本地 CPU）
- RAG pipeline：`hybrid_v2`（Dense + BM25 + RRF 融合 + CrossEncoder 重排）
- GraphRAG：`GRAPH_RAG_ENABLED=true`（活动索引 `rag-v2-20260824T024746251335Z-8d89f653`，活动图谱 `graph-20260824T032039458153Z-7a0729a2-2558bd4d`）
- PubMed：`PUBMED_ENABLED=true`，provider `mcp`（公开只读 MCP 端点）
- TOP_K（`RAG_TOP_K`）：4；FETCH_K：8；`RAG_MIN_SIMILARITY`：0.60
- 采样温度：由服务端默认值决定，脚本未覆盖（not available: 具体温度数值未在接口层暴露）
- 运行环境：本地开发机（Windows），复用开发虚拟环境；模型密钥仅存在于本地 `backend/.env`

## 7. 安全声明

- 本目录不含任何 API key、token 或其他凭证；重新运行需自备 `backend/.env`。
- `model_assisted_review.csv`（若生成）只是辅助材料，其内容不进入 `summary.json` 与 `report.md` 的正式指标。
- 本目录所有指标均以 `human_review.csv` 中的人工判定为唯一来源。
