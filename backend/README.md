# 疫苗科普 AI 后端

本目录是项目的正式 FastAPI 后端。它提供疫苗知识问答和 Wan 科学图解生成；模型密钥只保存在后端 `.env`，绝不能写入前端代码或提交到 Git。

## 当前推荐能力

| 能力 | 推荐接口 | 说明 |
| --- | --- | --- |
| 服务状态 | `GET /api/v1/health` | 检查服务是否可用。 |
| 疫苗知识问答 | `POST /api/v1/chat` | 返回疫苗相关问题的文字回答。 |
| 科学图解生成 | `POST /api/v1/image-jobs` | 推荐的生图入口：中文主题先整理为受约束的科学图解 brief，再交给 Wan。 |
| 查询图解任务 | `GET /api/v1/image-jobs/{job_id}` | 轮询任务状态，完成后得到图片地址。 |
| 获取图片 | `GET /api/v1/generated-images/{filename}` | 返回已完成任务的 PNG。 |
| KnowledgeGap 审核 | `/admin` | 单一管理员审核、预览 Markdown 并人工发布到 RAG。 |

> `/api/v1/knowledge-image` 是旧的兼容接口，使用 Z-Image，可能生成中文或非 9:16 图片。新前端不要使用它；请统一接入 `/api/v1/image-jobs`。

## 本地启动

要求：Python 3.10+。

```powershell
cd D:\project\挑战杯\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

编辑 `.env`，至少填入：

```text
DASHSCOPE_API_KEY=你的_DashScope_Key
```

启动正式后端：

```powershell
cd D:\project\挑战杯\backend
.\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000
```

启动成功后可打开：

- Swagger：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`
- 管理审核台：`http://127.0.0.1:5173/admin`

### 配置 KnowledgeGap 管理员

主站保持匿名，只有 `/admin` 需要登录。交互式生成 Argon2 哈希：

```powershell
.\.venv\Scripts\python.exe -m app.admin.cli
```

将输出的哈希和一个不少于 32 字符的随机会话密钥写入本地 `.env`：

```text
ADMIN_USERNAME=review-admin
ADMIN_PASSWORD_HASH=$argon2id$...
ADMIN_SESSION_SECRET=请使用独立随机长字符串
```

管理员批准 KnowledgeGap 时只生成 `runtime/knowledge_drafts/{gap_id}.md`；只有在前端预览后再次点击“发布到知识库”，才会把同一文件写入 `RAG/人工审核发布/`、调用现有完整 ingestion pipeline 构建版本化 NumPy exact dense candidate，并在 `RagService` 可检索且切换 active pointer 后标记为 `published`。当前是单实例同步 MVP，发布期间不要同时运行 CLI `build`。

## 科学图解：前端接入方式

### 1. 创建任务

前端只提交用户原始中文主题，不要传 `image_type`、参考图路径、模型名或 API Key。

```http
POST /api/v1/image-jobs
Content-Type: application/json

{"prompt":"解释疫苗接种后如何建立免疫记忆，请生成机制图解"}
```

响应示例：

```json
{"job_id":"62b9c559e1dd","stage":"preparing_content"}
```

### 2. 轮询状态

```http
GET /api/v1/image-jobs/62b9c559e1dd
```

处理中会依次出现 `preparing_content`、`generating_illustration`；完成时返回：

```json
{
  "job_id": "62b9c559e1dd",
  "stage": "completed",
  "image_type": "mechanism_diagram",
  "image_url": "/api/v1/generated-images/62b9c559e1dd.png",
  "error": null,
  "retryable": false
}
```

将 `image_url` 拼接到后端地址即可展示，例如：

```text
http://127.0.0.1:8000/api/v1/generated-images/62b9c559e1dd.png
```

图像同时保存在本地 `generated_images\{job_id}-v{version}.png`。默认流程通过 Wan 输出 9:16 PNG；启用细胞 IP skill 后通过同一 Wan 通路输出 16:9 横版手绘图。单次生成可能需要数分钟；同一时刻只允许一个图解任务运行。

### 3. 取消或重试

```text
DELETE /api/v1/image-jobs/{job_id}
POST   /api/v1/image-jobs/{job_id}/retry
```

仅失败或取消且保留了科学 brief 的任务可以重试。

## 图解生成的正式流程

```text
用户中文主题
  → Qwen 生成中文科学图解 brief
  → 自动选择 science_poster / graphical_abstract / mechanism_diagram
  → Wan（默认 9:16、单候选、按类型使用一张本地参考图）
  → 可选视觉审核与受框选范围保护的局部修订
  → generated_images/{job_id}-v{version}.png
```

当前默认候选数为 1，以缩短生成等待时间。不要把旧的 Z-Image 结果与这条链路的结果混在一起验收。

### 细胞 IP Skill

`CELL_IP_ENABLED=false` 为默认值，关闭时不读取或使用任何细胞 IP 资产，正式生图行为保持原样。设置为 `true` 并重启后端后，涉及细胞、病毒、抗原或抗体的正式 image job 会自动读取 `CELL_IP_SKILL_DIR` 指向的 `cell-ip-illustrations` skill；其他医学主题仍使用普通科学图解：

- 命中辅助性 T、B、记忆 B、细胞毒性 T、巨噬、树突状、红细胞、病毒、抗原或抗体时，优先使用 `assets/flat-characters/` 下对应的独立角色资产作为 canonical 参考。
- 参考图预算为 2 张：当需要的固定角色超过 2 个时，改为把 `assets/flat-character-sheet.png`（完整角色总表）作为单张参考图，并由提示词明确告诉模型从总表中提取哪些角色、保持哪些造型、忽略哪些角色。
- 未收录的必要细胞没有独立资产，沿用与总表一致的整体扁平手绘画风生成相容形象，不会冒充任一固定角色；角色资产不会被用来补造科学机制。
- 生成和局部编辑均使用最多两张 RGB 参考图（或单张角色总表），输出切换为 16:9。
- 视觉审核会比对本题角色参考；固定角色颜色、轮廓或专属道具明显不符且可定位时，最多自动局部修订一次，失败则转人工复核。
- skill、清单或必要资产缺失时后端启动失败，不会静默退回普通风格。

角色与别名的唯一运行时清单位于 `skills/cell-ip-illustrations/assets/manifest.json`；修改角色档案或文件名时必须同步更新该清单。

## 关键配置

配置项和默认值见 `.env.example`。最常用项：

```text
DASHSCOPE_API_KEY=...
QWEN_MODEL=qwen3.8-flash
QWEN_LIGHTWEIGHT_MODEL=qwen3.8-flash
GENERATED_IMAGE_DIR=./generated_images
IMAGE_JOB_CONCURRENCY=1
IMAGE_SOFT_DEADLINE_SECONDS=120
IMAGE_HARD_DEADLINE_SECONDS=150
CELL_IP_ENABLED=false
CELL_IP_SKILL_DIR=../skills/cell-ip-illustrations
```

修改 `.env` 后需要重启后端。不要提交 `.env`、`generated_images/`、OCR 缓存或运行日志。

## 本地 RAG 知识库

问答接口检索当前 active 的本地冻结索引，再让 Qwen 基于当轮片段回答，并返回服务器组装的 `sources`（文件名、1-based 页码、section、片段原文）。V2 使用 Docling 结构化语料、Dense+BM25/RRF、CrossEncoder reranker、轻量质量先验和 soft diversity；API 契约不变。

### 零经验启动

1. 创建并激活虚拟环境，安装依赖（含 PyMuPDF、sentence-transformers、NumPy；Chroma 仅用于 legacy 索引兼容）：

   ```powershell
   cd D:\project\挑战杯\backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e ".[dev]"
   ```

2. 复制 `.env.example` 为 `.env`，至少填入 `DASHSCOPE_API_KEY`；RAG 参数均有默认值，可选覆盖：

   ```text
   DASHSCOPE_API_KEY=你的_DashScope_Key
   RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
   RAG_MIN_SIMILARITY=0.60
   ```

3. 首次冻结由维护者在受控环境按“审计 → 候选 → 验证 → 激活”执行。Docling JSON 应先生成在 `runtime/docling_v2/{doc_id}.json`；模型下载只发生在准备阶段，运行时仅用本地缓存。公开仓库不包含生产运行时索引；项目报告 1081 条口径只公开方法、汇总指标和脱敏样例，另行建立的 RAG V2 X2 1000 条冻结复核 benchmark 则完整公开测试集、gold 与逐条结果，详见 [`docs/evaluation.md`](../docs/evaluation.md)：

   ```powershell
   .\.venv\Scripts\python.exe -m app.rag.cli corpus-audit
   .\.venv\Scripts\python.exe -m app.rag.cli build-v2
   ```

   `build` 仍保留为 legacy dense 对照/回滚命令，不是 V2 冻结入口。不要绕过 candidate validation 或受控审核直接激活索引。

4. 查看索引状态（不加载模型）与验证检索：

   ```powershell
   .\.venv\Scripts\python.exe -m app.rag.cli inspect
   .\.venv\Scripts\python.exe -m app.rag.cli query "EV71 疫苗预防什么？"
   ```

5. 添加或替换语料后必须重新完成 corpus audit、Docling、candidate build 和受控审核；FastAPI 启动不会自动解析或 embedding。

6. 扫描件/无文本层 PDF 必须明确记录 `no_text/OCR requirement`，或用 Docling OCR 生成结构化产物。重复、下载占位和 authority 0 不进入正式 candidate，但仍保留 manifest provenance。

7. `rag_index/`、`model_cache/`、`.env` 均不提交 Git。

### 问答接口的 sources 契约

`POST /api/v1/chat` 请求保持不变；成功响应增加 `sources`，无命中、非疫苗问题或预设本地回答时为 `[]`：

```json
{
  "question": "儿童轻微感冒时可以接种疫苗吗？",
  "session_id": "response-turn-1",
  "history": [
    {"role": "user", "content": "我想了解儿童接种前的注意事项。"},
    {"role": "assistant", "content": "可以继续问具体情况。"}
  ]
}
```

`history` 是可选的显式语义上下文。前端发送最近 8 条文本消息（约 4 个往返），仅供
Conversation Orchestrator 恢复“那第二针呢”“为什么”等省略式追问；它不替代
`session_id`，也不作为医学证据。主回答仍使用用户原始 `question` 和原有
`previous_response_id` 链，RAG 则使用 Orchestrator 生成的独立 `retrieval_query`。

```json
{
  "answer": "轻微感冒是否影响接种，需要结合是否发热、症状严重程度和疫苗种类判断；请在接种前如实告知医生，由接种人员现场评估。",
  "model": "qwen3.8-flash",
  "is_vaccine_related": true,
  "session_id": "response-turn-2",
  "sources": [
    {"file_name": "预防接种工作规范（2023年版）.pdf", "page": 12, "content": "接种工作人员在实施接种前，应询问受种者的健康状况……"}
  ]
}
```

`sources` 由后端检索层独立组装；API 不返回本地绝对路径、向量或相似度。LLM 被约束为不自行输出引用编号或文件名。

### 常见错误

| 现象 | 原因与处理 |
| --- | --- |
| 503 `本地知识库尚未建立，请先运行 RAG 建库命令。` | active/legacy 索引不存在；检查 `app.rag.cli inspect`，不要绕过 validation 直接写 pointer |
| 503 `AI 服务暂时不可用` | 索引 schema、模型或 chunk 参数不兼容；构建新 candidate 并重新评测，不能原地覆盖 active |
| reranker fallback | 本地 `BAAI/bge-reranker-base` 缓存不可用；服务退回 dense，正式冻结 eval gate 会拒绝该 candidate |
| DashScope 认证失败 | `.env` 的 `DASHSCOPE_API_KEY` 缺失或无效 |

## 本地 RAG 实施记录

- 2026-08-06 首版建立：10 份 PDF、8 个唯一哈希（两组二进制重复）、124 页可用、237 个切片，BGE-small-zh-v1.5 余弦索引。
- 《全民健康十万个为什么：免疫与接种》17 页均无文本层，已跳过并告警；首版不含 OCR。
- 当前默认 `RAG_MIN_SIMILARITY=0.60`。语料、切片或检索参数变化后，应在受控环境重新审核后再激活候选索引。

## 开发检查

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests
```

测试使用模拟客户端，不会调用真实模型或消耗额度。
