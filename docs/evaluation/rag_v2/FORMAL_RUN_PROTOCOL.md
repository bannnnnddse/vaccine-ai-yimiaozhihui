# RAG V2 正式评测冻结与运行协议

## 冻结边界

正式指标固定为 `metric_definition.json` 中的 chunk-level Top-4 命中规则。最终配置固定为 X2：Dense 50、BM25 50、RRF fusion 60、plain rerank 60、window rerank 60、邻接平滑 λ=0.9、`min_relevance=0.0`、soft cap=3、Top-K=4。

`python scripts/evaluate_rag_v2.py validate` 只在下列条件全部满足时生成冻结文件：

- 正式测试集、gold、指标定义和 corpus manifest 可读且满足结构约束；
- 生产检索代码和评测脚本已经提交，工作区中的冻结源文件与 HEAD 一致；
- 旧的正式输出、run state 和 checkpoint 已隔离；
- 活动 index 中包含全部 gold，index 文件与 corpus 身份可计算哈希。

生成的 `config_snapshot.json` 记录 commit、index、配置、指标、生产源文件、测试集、gold、corpus 和 index 文件哈希；`freeze_manifest.json` 再记录 config snapshot 自身的哈希。正式运行和汇总都会重新验证这些冻结值。

## checkpoint 与无效运行

`run` 首次启动时生成唯一 `run_id`、`formal_run_state.json` 和 `formal_checkpoint.json`。每条 case 的 result 与 trace 都执行 flush + fsync，随后原子更新 checkpoint。恢复时要求 result/trace 的 case ID 序列完全一致、没有重复、数量与 checkpoint 一致；否则自动把本次运行记为 invalid。

模型异常、pipeline fallback 或其他逐 case 异常会立即停止并在 `invalid_runs.jsonl` 留下不可覆盖的审计记录。人工判定运行无效时使用：

```powershell
python scripts/evaluate_rag_v2.py invalidate --reason "明确、可审计的原因"
```

进程意外退出但已持久化的 result、trace 和 checkpoint 三者一致时，允许对同一 `run_id` 执行 `run` 恢复；不得删除单个失败 case、选择性重算或在查看 final 指标后更改算法。无效运行的全部文件必须整体归档后，才能重新 validate 并从 case 1 开始完整运行。
