> 历史部署记录来源：开发/生产项目提交 `2465df8`（2026-10-07）。所述运行配置、耗时、验证数量和部署状态属于该历史环境。

# NCBI Direct 部署（2026-10-07）

用户明确授权替代生产 MCP 检索方案。生产 `PUBMED_PROVIDER=direct`，保持 mihomo 专用代理与 `PUBMED_TIMEOUT_SECONDS=0`。后端镜像已重建，健康检查通过。源代码默认值、配置样例、README、部署文档和 AGENTS 同步；源码仍未提交或推送。

复用现有 DirectPubMedProvider，应用 lifespan 共享 HTTP AsyncClient 并在关闭时清理。检索采用 ESearch → 批量 EFetch；无 API key 时通过共享 provider 锁保证本实例请求间隔至少 0.34 秒，若配置 key 则至少 0.11 秒。没有建立 MCP 会话或重新下载模型。原活动 Vector/Graph pointer 未改变，GraphRAG 保持开启。

隔离容器中验证 PubMed 提供方、默认配置、工具编排、问答和 health，共 137 个不同用例通过。Settings 默认值测试单独运行，排除问答测试临时数据库环境变量的影响。Ruff 与源码、运行时部署预检通过。

使用生产配置共享一个 HTTP 客户端进行两题只读真实检索，不调用模型：

| 查询 | 检索编排耗时 | 保留文章 | 有摘要 |
| --- | ---: | ---: | ---: |
| HPV vaccine | 2.122 秒 | 2 | 2 |
| influenza vaccine | 1.688 秒 | 2 | 0 |

均返回有效 PubMed URL。流感样本保留的论文没有摘要，现有最终回答仍须限制证据表述；此记录不是医学准确率验收。以上耗时不包含本地 RAG、工具指令模型和最终回答生成，不保证后续网络耗时。完整 PMID 与 trace 见相邻 JSON。

官方依据：[NLM ESearch/EFetch 参数](https://www.nlm.nih.gov/dataguide/eutilities/utilities.html)、[NCBI 请求速率说明](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/amp/)。

回退可将生产提供方设为 `mcp` 并重建后端容器；部署前镜像保留为 `vaccine-ai-backend:before-pubmed-direct`，生产配置备份保存在本次私密部署目录中。
