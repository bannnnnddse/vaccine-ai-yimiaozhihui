# RAG V2 X2 迁移验证

本文记录从实验仓库到目标仓库的白名单迁移。正式 1000 条结果来自冻结实验运行；目标仓库未重新筛选测试集、未修改 gold、未删除失败案例，也未重新运行正式评测。目标仓库通过实现增量、配置、冻结文件 hash 和回归测试承接该结果。

## Git 身份

- 实验冻结 commit：`a50d3cc6ba62c5876323cbd189848d4e75a39fd2`
- 目标迁移前 commit：`aa23c4a7a8ee2747ca32155c1f3187e37f997899`
- 目标 port commit：`3caa5979380f5a59d6beba30ce0aa1f7cf51093c`
- 本文件的回填由后续独立 documentation commit 完成，以避免同一 commit 自引用；该 documentation commit 不改变生产代码或冻结证据。
- 目标分支与发布远端：`main` → `yimiao/main`

## 冻结输入

- evaluation cases：`a454d3e4ea3d09d55cf6d0fd4db7f7b63b66d261aed1abdd336561be0e84123d`
- gold labels：`aea4a83dd4e4f3ccab3afeecbae7794f413eae11cb68b4f5cc3c0fba692973d0`
- evaluator：`adfe111bc7b6fd681cc61524bad28cdb50fcb09d65ac99398fce139411c975c5`
- summary：`e78192fc30f63f415e149e4bfd6d262e7c15eb5cb4db57f4c832b55cb661c858`
- raw results：`ecd5c89d09d71f1c6cf4c659b563890631fa58fb3553340d6fcdb453e37cdcdb`
- raw traces：`3e32cb59bbc52fd61e6394a85a94abb232bdd9e3d2d631b0efbc6ed1c8c3d0fb`
- failure cases：`c1bc4abcfe535d36ddd1b1c35d99daf8a59dedc9d5d084f82514da8a4974f12e`
- freeze manifest：`e7c156443d2cc04b810ddd18a92d4aa75b49552a8d78f7baea30b5f35a9355af`
- index version：`rag-v2-20260824T024746251335Z-8d89f653`（索引本体不公开）

## 生产实现等价性

实验仓库四个冻结文件的 SHA256：

| 文件 | 实验 SHA256 | 目标 SHA256 | 结论 |
| --- | --- | --- | --- |
| `backend/app/core/config.py` | `4fdb86113eac7fca01d03d57549f1008dec16d524709dc559bfc9fc93688430e` | `922f8c0099e9b97e9d2be504b1c5219ccdc5e1d97d91d073e9111235a56aeb03` | X2 默认值相同；目标额外保留模型 revision 与 citation audit 配置 |
| `backend/app/rag/ranking.py` | `1b4c8b01c88ce207a2591011be8f9756b4ab06c624bd3dde3f7cdae59a945d1a` | `e2c2d72e33d8b8437deba2e247415e12ae9574ce1be6e072c008c116f81289bf` | 忽略行尾差异后无内容差异 |
| `backend/app/rag/reranker.py` | `e1774a2cf10e724fc25b737be5c6780b06f50907bba0ffd477ee8694f9a4e9f4` | `f0e0269192a1036fcbf5a4480206ddbb094c901dff026ad6ab35e733a108f327` | X2 window/max 合并相同；目标额外固定 plain/window 模型 revision |
| `backend/app/rag/service.py` | `735db57a57d6dccd35dced5b4ad6118f5066bf49d601cce01fd27a3fca5aebff` | `6ee330fbe7c29c21a88b28192ea4532d728c8b78b8191fe04d7faea209bd369f` | X2 编排相同；目标额外传递模型 revision 与 source document_id |

目标仓库在冻结实验 commit 之后已有模型 revision 固定、citation entailment 审计和 `RagSource.document_id` 来源去重修复。迁移保留这些目标侧安全/可复现性增强，所以部分文件预期不会 byte-identical；X2 的候选深度、窗口重打分、max 合并、邻接平滑、质量先验和 soft-cap selection 必须由差异审计与测试证明逻辑等价。

## 实际生效配置

`dense=50`、`lexical=50`、`fusion=60`、`rrf_k=60`、`plain rerank=60`、`plain batch=16`、`plain max_length=256`、`window enabled`、`window max_length=512`、`prev/next=300/300`、`window batch=8`、`neighbor λ=0.9`、`min_relevance=0.0`、`max_chunks_per_document=3`（soft cap）、`near_duplicate=0.94`、`top_k=4`。

## 验证结果

- pytest：428 passed，2 warnings（旧 405 基线之后目标仓库新增 citation/source 测试，并加入本次 X2/evaluator 回归）
- ruff：`ruff check app tests` 全部通过
- 前端：59 个测试文件、348 项通过；`pnpm build` 通过（仅有既有大 chunk 提示）
- deploy preflight：`python scripts/deploy_preflight.py --source-only` 通过
- 冻结指标独立复算：X2 815/1000、baseline 669/1000、差值 +146/+14.6pp；1000 个 result ID 与 1000 个 trace ID 顺序一致；185 个 miss 全部保留；error=0
- 敏感信息审计：已检查 staged 白名单；命中仅为环境变量名称、公开 DashScope URL、`your_api_key_here`、空值及测试 placeholder，没有发现真实凭证

`consistency_report.json` 记录 500 条缓存 dev case 的逐阶段一致性：dense `261f7247…`、lexical `a492a9c4…`、fused `a0b8b9e2…`、reranked `8c9706bb…`、quality `dc00bbf2…`、selected `57ff6984…`，结论为 500/500 的生产编排一致。dev-500 包含全部 331 个 baseline miss 与 169 个抽样 hit，不是独立未知 holdout。
