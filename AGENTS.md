# 疫苗防线项目状态与维护指南

_本文件是仓库当前完成状态、系统边界和后续维护约束的唯一入口。运行代码与测试优先于 README 和历史报告。_

---

## 📍 交付状态

项目已完成可演示的全栈交付版本：React/Vite 前端、FastAPI 后端、受治理本地 RAG、受限 PubMed 核验、科学图解任务、免疫互动、管理员知识治理和只读知识图谱查看器均已实现。后续工作只能以修复缺陷、提升可访问性/性能、补充受控语料或获得明确授权后的图谱评估与发布为目标。

当前本地离线验证基线（2026-10-09；不代表线上医学准确性验收）：

- 在线体验地址（Cloudflare 隧道实时演示）：https://skin-swimming-shades-assume.trycloudflare.com/ （临时隧道，服务器重启后地址可能变化；部署细节见 DEPLOYMENT.md）
- 前端 `pnpm test`：62 个测试文件、377 项测试通过；`pnpm typecheck` 与 `pnpm build` 通过
- 后端 `pytest`：450 项测试通过（2 个第三方 deprecation warnings；含图解证据绑定与生命周期守护回归）；`ruff check app tests` 通过
- `python scripts/deploy_preflight.py --source-only` 通过
- GitHub Actions 配置覆盖 `main` 与 `master` 的前端、后端和 Docker 构建检查；实际通过状态以对应提交的 CI 输出为准
- 项目提交报告口径：Top-4 evidence retrieval 为 958/1081（88.62%）；该口径先从 1500 条中按当时语料覆盖排除 419 个 Knowledge Gap
- 冻结 RAG V2 X2：Top-4 chunk recall 为 815/1000（81.5%），同集 baseline 为 669/1000（66.9%），提升 +146 hits / +14.6 percentage points；该指标不是回答或医学正确率

> ⚠️ **能力声明边界：** 清单共 141 条（125 PDF + 12 MD + 4 DOCX，含 4 份下载占位），不等于实际入索引的文档数。历史部署记录：索引 `rag-v2-20260824T024746251335Z-8d89f653` 为 17,167 chunks，图谱 `graph-20260824T032039458153Z-7a0729a2-2558bd4d` 为 8,006 节点、6,215 边、5,282 条 provenance。生产快照不随 Git 发布，代码默认 `GRAPH_RAG_ENABLED=false`，线上配置需单独核验。图缺失或版本不匹配时问答退回 Vector-only。科普视频可在 [线上演示网站](https://www.yimiaozhihui.cn/) 观看；仓库仅附封面，本地部署需另行提供 MP4。视频页播放预制短片，不提供实时视频生成。

2026-10-08 已新增中国疾控收录的狂犬病 2023 年版规范原件与结构化正文，候选 6 个条款正例、2 个负例检索检查全部通过。源文件与验证记录随 Git 交付，生产 active pointer 未切换；当前20条已完成导师审核；SCI-013选用独立复核的新返回，旧SCI-013引用争议保留历史记录。见 [接入记录](docs/rabies-corpus-integration-2026-10-08.md)。

## 🧭 五模块闭环

| 模块 | 主路径 | 闭环与人工控制 |
| --- | --- | --- |
| 问答 | 问题 → 路由 → Hybrid RAG → 证据评估 → 回答与来源 | 证据不足形成可审核的 KnowledgeGap；不自动入库 |
| 图解 | 主题 → 独立 RAG → brief 与来源绑定 → 支持检查 → Wan → 审查/编辑 | 用户确认采用并处理不确定或越界修改 |
| 互动 | 三个顶层阶段的免疫叙事与简化传播模拟 | 五关卡为早期叙事设计；当前模拟没有资源配置参数 |
| 知识治理/图谱 | 候选主张 → 人工审核 → 草稿 → 候选版本 → 原子发布 | 管理员可驳回/暂缓/批准；图谱构建须获得明确授权 |
| 前端体验 | React 状态与服务层 → 异常/取消处理 → 测试 → 人工验收 | 保持 keyboard/focus、移动端、reduced-motion 与清理异步资源 |

完整模块流程、架构与交付入口见 [README.md](README.md)；运行代码与测试仍是最终事实来源。

## 🏗️ 当前架构

| 层级 | 组件 | 责任边界 |
| --- | --- | --- |
| 前端 | React 19、TypeScript、Vite、Cytoscape | 只调用同源 `/api/v1`；网络代码只在 `frontend/src/services/`；跨面板状态在 `App.tsx` |
| API | FastAPI 应用工厂、`/api/v1` router、lifespan | 路由只做 HTTP/依赖/稳定错误映射；共享客户端和服务由 lifespan 创建 |
| 问答 | `RagService`、`QwenService`、`EvidenceAssessmentService` | 主回答看到原问题；来源只能由当轮检索/外部文献产生 |
| 知识 | `RAG/`、manifest、versioned candidate、`active.json` | 服务运行时只读本地模型和索引；仅显式 bootstrap 可下载固定模型并本机重建功能级索引 |
| 治理 | KnowledgeGap、管理员 session/CSRF、SQLite GraphJob | 只允许人工批准、人工发布；失败保留旧活动版本 |
| 图解 | ImageJob、organizer、Wan、critic、scope guard | 单活动内存任务；取消、轮询和请求必须对称清理 |
| 图谱 | graph worker、validator、snapshot、public store | 唯一输入为同版 Vector candidate chunks；不重新解析 PDF 或写向量库 |

## 🧠 模型与规则分工

默认模型名可由环境变量覆盖；实际部署以 `backend/.env` 为准，密钥不得被提交、记录或回显。

| 组件 | 默认角色 | 强制边界 |
| --- | --- | --- |
| Qwen `qwen3.8-flash` | 路由、追问恢复、证据评估、受证据约束回答、PubMed 工具编排、图解 brief、视觉审查、离线图谱候选抽取 | 不生成来源；不绕过证据给具体医学结论；不自动批准或发布知识 |
| Wan `wan2.7-image-pro` | 根据已整理 brief 生成科学图解和受 bbox 限制的局部编辑 | 不作为科学事实判定器；输出必须经过审查与用户确认 |
| BGE embedding | 本地 Dense 召回与候选索引构建 | 不生成语言或医学结论 |
| BM25 | 中文关键词、专名和稀有词的词法召回 | 不替代语义重排或证据准入 |
| RRF + CrossEncoder | 融合 Dense/BM25 并对有限候选重排 | 不替代人工审核、来源 provenance 或版本校验 |
| 图谱规则验证器 | 同 chunk 逐字 surface/quote、受控类型/关系、否定/不确定性、domain-range 与 provenance 校验 | 无法确认时宁可拒绝；不使用自动 NER/fuzzy merge 绕过校验 |

## 🔁 关键运行不变量

### 问答与来源

- `POST /api/v1/chat` 输入为 `question`、可选 `session_id` 和最近显式 `history`；输出固定包含 `answer`、`model`、`is_vaccine_related`、新 `session_id` 和 `sources`
- 自由问答只使用最近 8 条已完成文本作为 history；前端遇到 session 409 只清 session 后重试一次，不能丢弃 history
- RAG 事实回答必须基于当轮独立 V2 检索；主回答不得将改写 query 或 history 当作医学证据
- EvidenceAssessment 仅评估 Vector Top-K；partial/insufficient/conflict 或显式最新研究最多进入两轮受限 PubMed loop
- `sources` 只能来自当轮本地检索或外部 PubMed；PDF 页码为 1-based；无证据时为 `[]`
- 证据不足且 PubMed 无结果时返回受限初步科普，不捏造剂次、年龄、禁忌或来源；网络超时才返回 504

### 知识治理与图谱

- PubMed 是当轮只读外部来源，绝不能自动写入 RAG 或图谱
- 管理员审批只生成草稿；发布由持久化 GraphJob 串行执行，全部校验成功后才原子更新活动版本
- 图谱快照必须绑定同版 index；图缺失、损坏或版本不匹配时公共图 API 返回 503，问答安全退回 Vector-only
- 真实模型调用、图谱 worker、全库构建或任何可能产生费用的操作必须先取得用户明确授权

### 图解与前端生命周期

- 正式图解 API 固定为 `POST /api/v1/image-jobs`、`GET /api/v1/image-jobs/{id}`、`DELETE` 取消；不得新增旧 `/knowledge-image` 调用
- 当前任务阶段以 `app/schemas/knowledge_image.py` 与 `science_image_job_manager.py` 为准，包含 `rewriting_prompt`、`generating`、视觉审核/修订及终止状态；历史 `preparing_content` / `generating_illustration` 不代表当前管线发出的完整状态
- 正式任务必须经过 `ScienceImageEvidenceService`：独立调用共享 RAG、记录本轮 index version、校验每个 claim/step 的来源及逐字摘录，再进行支持范围检查；失败不得调用 Wan。重试重新检索；编辑只能保留已绑定科学含义，否则要求新主题。来源与图片元数据、前端结果及会话历史同属一个任务，不能把来源绑定或模型支持检查称为医学审核通过。旧空白名单保持删除；图解未接 PubMed，不得用聊天历史当证据
- 互动入口保留科普与医疗建议的边界提示；测试不得断言免责声明必须不存在
- `DELETE /image-jobs/{id}` 只有工作任务与阻塞图像线程退出并清理后才返回 `job_id + cancelled=true + stage`；后端等待上限 8 秒，前端含响应体读取上限 10 秒。超时/创建中断/刷新需保存“停止未确认”，结果归属原对话且不复活已删除记录；不能把应用侧取消确认表述为供应商已退款。
- 图解创建、轮询、编辑与接受必须使用 request token、job ID 和 AbortController；切换、取消、卸载时清理 timer、poll、listener、observer、GSAP 和请求
- `CELL_IP_ENABLED` 仅表示固定细胞 IP 能力可用，不能覆盖普通科学图解默认的 `scientific_diagram` profile

## 🧪 质量、仓库与发布规则

- RAG 检索采用两套不同用途的口径：1081/88.62% 是项目提交报告采用的评测；1000/81.5% 是后续建立的完整公开、冻结可审计 benchmark。两者测试集构造与协议不同，不是前后成绩、不可横向比较，也不得用其中一个覆盖另一个
- 冻结 RAG V2 1000 条评测公开测试集、gold、逐条结果、trace、全部失败案例、baseline、配置与 hash manifest，见 `docs/evaluation/rag_v2/`；报告口径的原始 1081 条逐题数据仍未公开，仅提供脱敏样例。调参 dev-500 含全部 331 个 baseline miss，不得称为独立未知 holdout
- 该 1000 条 benchmark 的可接受 gold 仅覆盖 220 个不同 chunk，4000 个 Top-4 项仅覆盖 543 个不同 chunk；不得据此宣称跨主题泛化已验证
- SCI-013 已通过指定候选索引真实重跑，返回新增规范第七条；新记录位于 `docs/evaluation/scientific_correctness/reruns/`，已独立绑定导师评分并按指定样本版本纳入当前20条指标，生产活动版本未切换。
- 科学正确性当前20条样本已完成导师审核；SCI-013采用独立复核的新返回，SCI-020引用支持为0。由 `sample_selection.json` 和 `review_status.json` 指定样本与评分对应，不能仅凭分数相同自动继承旧评分，不能把不同版本输出描述为同一次冻结运行。
- 正式评测证据冻结后不得重筛 case、修改 gold、删除失败案例或用重跑结果覆盖；构造脚本不得进入 CI/生产自动流程。RAG X2 是 recall-oriented 配置，CPU 正式评测平均延迟约 39 秒，不得声称低延迟
- 代码、配置与测试优先于实施报告；历史文档不得覆盖当前运行事实
- 不提交 `.env`、密钥、`backend/runtime/`、`backend/rag_index/`、`backend/model_cache/`、`backend/generated_images/`、运行日志、虚拟环境或编译缓存。功能级复现由 `assets/runtime-assets-manifest.json` 固定官方模型 revision，并由 bootstrap 从受治理语料本机生成索引；下载后必须实际离线加载验证。不得发布生产 active 索引或 Graph snapshot，因为它们含完整 chunk/provenance 正文与生产历史。长期约束与操作入口见 [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md)；受治理语料与源码、测试随仓库交付。
- 根目录 `.git` 是唯一仓库；`backend/` 与 `frontend/` 是普通目录，统一从根目录执行 Git 操作
- 不使用 `git reset --hard`、`git checkout --` 或 stash 覆盖未知改动；不删除未确认的本地忽略文件
- 推送前运行 `python scripts/deploy_preflight.py --source-only`；服务器补齐私密资产后运行完整预检，部署细节见 [DEPLOYMENT.md](DEPLOYMENT.md)

## ✅ 后续维护检查清单

改动问答、RAG、来源、session、图谱上下文时，同步后端 schema/routes/services/tests 与前端 service、生命周期、sources 渲染和测试。改动图解时，手工检查桌面、常见横屏、≤720px、键盘、focus、reduced-motion、加载与错误状态。改动实体/关系/prompt/validator 时，升级对应版本签名并补正例、负例、别名、歧义、否定和注入测试；不得用真实模型或真实网络测试替代这些检查。

```powershell
cd frontend
pnpm test
pnpm build

cd ..\backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

语料书目信息核对入口：[docs/corpus-review/README.md](docs/corpus-review/README.md)。141 条导出记录保留原始元数据与哈希，人工只填结果列；文献类型核对不等于医学审核，禁止直接据此把清单改成 `human_approved` 或切换活动索引。
