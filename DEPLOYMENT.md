# 云服务器部署与复现

本项目是单一 Git 仓库。仓库为**完整交付快照**：GitHub 保存源码、构建配置、受治理语料，以及已构建的 RAG 索引、模型缓存、图谱快照、运行时数据库与历史生成图片（约 3.9GB），以便评审与离线复现。唯一不进入 Git 的是密钥文件 `backend/.env`；另有 14 个超过 GitHub 单文件 100MB 硬限制的文件未能入库（见下文清单），需通过私密部署通道补充。

## 服务器要求

- Linux x86-64，建议至少 8 GB 内存和 10 GB 可用磁盘。
- Docker Engine、Docker Compose v2、Git、Python 3.10+、curl。
- 能访问 Python、Node、PyTorch 及系统包镜像；首次无缓存构建需要网络。
- 生产域名应配置 HTTPS。Compose 内部只监听 HTTP 80；`ADMIN_COOKIE_SECURE=true` 时必须由外层反向代理终止 TLS。

## GitHub 中应当存在的内容

首次部署：

```bash
git clone <repository-url> vaccine-ai
cd vaccine-ai
python3 scripts/deploy_preflight.py --source-only
```

更新部署：

```bash
git fetch origin
git switch main
git pull --ff-only origin main
```

不需要也不应使用 `git submodule`。`backend/` 和 `frontend/` 必须随根仓库直接出现。

## GitHub 之外必须传输的内容

**必须传输的只有一项：**

```text
backend/.env
```

仓库已包含 `backend/rag_index/`（含 `active.json` 与全部版本目录）、`backend/model_cache/`（BGE embedding 与 reranker 权重）、`backend/runtime/`（含活动图谱快照、`app.db` 与审核草稿）以及 `backend/generated_images/`，克隆后即可运行完整预检。

**因 GitHub 单文件 100MB 限制未入库的 14 个文件**（需从已验证环境按私密通道补齐）：

```text
backend/model_cache/models--BAAI--bge-reranker-base/snapshots/2cfc18c9415c912f9d8155881c133215df768a70/model.safetensors   # 1060 MB
backend/runtime/docling_v2/doc_7f1e00587c6217d3764dce48.json                                                              # 436 MB
backend/runtime/chroma-16k-long-scoavkb6/chroma.sqlite3                                                                   # 171 MB
backend/runtime/probe_full_sync100/chroma.sqlite3                                                                         # 177 MB
backend/runtime/probe_payload_full/chroma.sqlite3                                                                         # 180 MB
backend/runtime/probe_payload_documents/chroma.sqlite3                                                                    # 147 MB
backend/rag_index/versions/rag-v2-20260816T040851213042Z-32af4353.failed-chroma-relocation/chroma.sqlite3                 # 100 MB
backend/rag_index/versions/rag-v2-20260816T042012671723Z-32af4353.failed-partial-hnsw/chroma.sqlite3                      # 100 MB
backend/rag_index/versions/rag-v2-20260816T043637335517Z-32af4353.failed-real-hnsw-persist/chroma.sqlite3                 # 100 MB
backend/rag_index/versions/rag-v2-20260816T045804106551Z-32af4353.failed-hnsw-compaction/chroma.sqlite3                   # 100 MB
frontend/public/assets/science-videos/virus-adventure-episode-1.mp4                                                       # 142 MB
frontend/public/assets/science-videos/vaccine-defense-episode-2.mp4                                                       # 104 MB
frontend/dist/assets/science-videos/virus-adventure-episode-1.mp4                                                         # 142 MB
frontend/dist/assets/science-videos/vaccine-defense-episode-2.mp4                                                         # 104 MB
```

说明：活动索引 `rag-v2-20260824T024746251335Z-8d89f653` 的全部文件与活动图谱快照 `graph-20260824T032039458153Z-7a0729a2-2558bd4d` 均**在仓库中**，上述缺失文件仅涉及失败构建的历史索引版本、开发期 Chroma 探针库、一个 docling 中间产物、reranker 主权重文件和两个科普视频，不影响当前活动版本的加载与问答。

当需要用验证环境的资产覆盖仓库快照时（例如模型权重更新后），使用私密传输通道：

```bash
rsync -a backend/rag_index/ user@server:/srv/vaccine-ai/backend/rag_index/
rsync -a backend/model_cache/ user@server:/srv/vaccine-ai/backend/model_cache/
rsync -a backend/runtime/graph/ user@server:/srv/vaccine-ai/backend/runtime/graph/
```

在服务器上单独创建 `backend/.env`，以 `backend/.env.example` 为模板填写真实密钥。至少检查 `DASHSCOPE_API_KEY`；若启用管理员功能，`ADMIN_USERNAME`、`ADMIN_PASSWORD_HASH`、`ADMIN_SESSION_SECRET` 必须同时设置，且会话密钥至少 32 字符。不要把 `.env` 或任何真实密钥提交到 Git。

## 权限与部署

容器内后端以 UID/GID `10001` 运行。完成资产传输后：

```bash
mkdir -p backend/runtime backend/generated_images backend/rag_index backend/model_cache
sudo chown -R 10001:10001 backend/runtime backend/generated_images backend/rag_index
sudo chmod -R a+rX backend/model_cache RAG
```

执行完整预检和部署：

```bash
python3 scripts/deploy_preflight.py
bash scripts/deploy_server.sh
```

预检会验证环境配置、活动索引、模型缓存、图谱版本以及 index/graph 版本绑定，但不会显示密钥内容。

## 部署后检查

```bash
docker compose ps
curl --fail http://127.0.0.1/api/v1/health
curl --fail http://127.0.0.1/
```

还应人工检查普通问答、RAG 来源、知识图谱、管理员登录和图片任务。升级前备份 `backend/runtime/app.db`、活动索引指针和对应版本目录；失败时回退 Git commit，并恢复同一组索引与图谱资产，不能混用版本。
