# RAG V2 X2 冻结正式评测

本目录公开 RAG V2 X2 的冻结正式评测证据。当前推荐引用的结果是：

| 配置 | Top-4 chunk recall | 命中数 |
| --- | ---: | ---: |
| baseline | 66.9% | 669 / 1000 |
| X2 | 81.5% | 815 / 1000 |
| 增量 | +14.6 percentage points | +146 |

该指标只判断正确 evidence chunk 是否进入生产检索链路最终 Top-4，不表示回答准确率、医学正确率或系统总体准确率。X2 的 Top-1 为 477/1000（47.7%），MRR 为 0.6204；CPU 正式评测平均延迟 39085.3 ms、P95 49831.9 ms，因此这是 recall-oriented 配置，不是低延迟生产配置。

## 冻结边界

- 实验仓库冻结 commit：`a50d3cc6ba62c5876323cbd189848d4e75a39fd2`
- 活动索引版本：`rag-v2-20260824T024746251335Z-8d89f653`
- 测试集 SHA256：`a454d3e4ea3d09d55cf6d0fd4db7f7b63b66d261aed1abdd336561be0e84123d`
- gold SHA256：`aea4a83dd4e4f3ccab3afeecbae7794f413eae11cb68b4f5cc3c0fba692973d0`
- evaluator SHA256：`adfe111bc7b6fd681cc61524bad28cdb50fcb09d65ac99398fce139411c975c5`
- config snapshot SHA256：`51ae5611b17afb0bf174ccb265b55d7e2049c19a5866e2645b0e305d6ae662ab`
- freeze manifest SHA256：`e7c156443d2cc04b810ddd18a92d4aa75b49552a8d78f7baea30b5f35a9355af`

`config_snapshot.json` 固定生产代码、检索设置、指标、corpus 与索引文件身份；`freeze_manifest.json` 再固定快照与 evaluator。正式 1000 条结果来自该冻结实验运行，迁移到本仓库时没有重新筛选 case、修改 gold、删除失败案例或重跑正式评测。

## 证据文件

- `metric_definition.json`：Top-4、Top-1、MRR 与 error 判定。
- `evaluation_cases.jsonl` / `gold_labels.jsonl`：冻结问题与可接受 gold。
- `config_snapshot.json` / `freeze_manifest.json`：配置、代码、corpus 与 index 身份。
- `raw_results.jsonl` / `raw_traces.jsonl`：全部 1000 条逐例结果与逐阶段 trace。
- `failure_cases.jsonl`：全部 185 个 Top-4 miss，没有筛除。
- `summary.json` / `formal_run_state.json`：正式汇总与完成状态。
- `baseline/`：同一 1000 条测试集的 baseline 配置、汇总和逐例结果。
- `consistency_report.json`：dev-500 在冻结缓存分数上的生产编排逐阶段一致性证明。
- `FORMAL_RUN_PROTOCOL.md`：冻结、checkpoint、恢复和 invalid-run 审计规则。
- `PORTING_VERIFICATION.md`：实验仓库到本仓库的代码、hash、测试与 Git 审计。

## X2 固定配置

Dense 50、lexical 50、fusion candidate 60、RRF k=60、plain rerank depth 60（batch 16，256 tokens），窗口重打分 depth 60（前后各 300 字符，batch 8，512 tokens），有效相关度取 `max(plain, window)`，候选池内 ±1 邻接平滑 λ=0.9，既有 quality prior 不变，`min_relevance=0.0`，soft cap=3 的 diversity-first selection，最终 Top-K=4。

soft cap 的含义是：主选择阶段优先遵守每文档 3 个 chunk；若无法填满 Top-4，overflow 才可超过 cap。它不是 hard cap。

## 测试集构造透明度

仓库根目录的 `scripts/build_rag_v2_candidates.py` 与本目录 `exclusions.jsonl` 用于记录正式测试集构造与排除过程，不是生产运行时代码。构造脚本可能调用外部模型，不在 CI 或生产部署中自动执行；正式结果生成后不得通过重跑筛选来更改冻结测试集。`build/` 中的 raw/screen 中间工件不属于公开证据包，也不纳入提交。

调参阶段的 dev-500 包含全部 331 个 baseline miss 和 169 个抽样 hit，不是独立未知 holdout。历史文档中的 `1081 条 / 88.62%` 来自不同数据集与不同筛选口径，不能与本结果横向比较。

## 离线复核

第三方可以直接读取 `raw_results.jsonl` 与 `baseline/raw_results.jsonl`，分别统计 `top4_hit=true` 的条数；该操作不调用检索模型，也不会生成新正式成绩。`scripts/evaluate_rag_v2.py` 的 `validate/run/summarize` 面向完整冻结运行协议，除非明确开展新的独立评测，不应使用它覆盖本目录的冻结结果。
