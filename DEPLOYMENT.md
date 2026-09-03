# 云服务器部署与复现

本项目是单一 Git 仓库。GitHub 保存源码、测试、受治理语料和构建配置；密钥、RAG 索引、模型缓存、图谱快照、数据库、生成图片及运行日志不进入 Git，必须通过私密部署通道提供。

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

从已验证环境通过 SSH、受控对象存储或备份系统传输：

```text
backend/.env
backend/rag_index/active.json
backend/rag_index/versions/<active index_version>/
backend/model_cache/models--BAAI--bge-small-zh-v1.5/
backend/model_cache/models--BAAI--bge-reranker-base/
backend/runtime/graph/versions/<active graph_version>/
```

需要保留管理员数据与发布任务状态时，还应传输：

```text
backend/runtime/app.db
backend/runtime/knowledge_drafts/
```

`generated_images/` 是可选历史产物，不影响源码构建。另因 GitHub 单文件 100MB 限制，两个科普视频未随仓库发布，需要完整视频演示时一并传输：

```text
frontend/public/assets/science-videos/virus-adventure-episode-1.mp4
frontend/public/assets/science-videos/vaccine-defense-episode-2.mp4
```

不要把 `.env` 或运行时资产提交到 GitHub。

示例传输命令需按实际服务器地址修改：

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
