#!/usr/bin/env python3
"""RAG V2 candidate builder: evidence-first question generation, screening, freezing.

Stages (run in order):
  generate  Select high-quality gold chunks from the ACTIVE rag index and ask
            the production Qwen model to write one natural public question per
            seed chunk. Difficulty quotas are assigned BEFORE any retrieval.
  screen    Rule-based filters + LLM quality screening. Every rejected
            candidate is recorded in exclusions.jsonl with a concrete reason.
            "预计召回困难" is not a valid reason and is never used.
  select    Freeze exactly 1000 cases (55/35/10 difficulty quotas), expand
            acceptable gold chunks within the same document, and write
            evaluation_cases.jsonl + gold_labels.jsonl.

This script never reads retrieval results and never touches the RAG runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "evaluation" / "rag_v2"
BUILD_DIR = OUT_DIR / "build"

CANDIDATES_RAW = BUILD_DIR / "candidates_raw.jsonl"
SCREEN_RESULTS = BUILD_DIR / "screen_results.jsonl"
EXCLUSIONS = OUT_DIR / "exclusions.jsonl"
CASES_PATH = OUT_DIR / "evaluation_cases.jsonl"
GOLD_PATH = OUT_DIR / "gold_labels.jsonl"

TARGET_CANDIDATES = 1265
FINAL_TOTAL = 1000
FINAL_QUOTAS = {"easy": 550, "medium": 350, "hard": 100}
QUESTIONS_PER_CHUNK = 5
FREEZE_SEED = 20260904

# Per-document question caps keep the pool from over-focusing on few documents.
DOC_TITLE_BLACKLIST = ("统计年鉴", "Ã")  # statistical tables / mojibake titles
FINAL_DOC_CAPS = {"official_document": 250, "official_web": 200, "academic_paper": 150}
DOC_PRIORITY = {"official_document": 0, "official_web": 1, "academic_paper": 2}

BANNED_QUESTION_PATTERNS = [
    r"\.pdf",
    r"\bdoc_",
    r"\bchk_",
    r"规范第\s*\d",
    r"第\s*\d+(\.\d+)+\s*条",
    r"知识库",
    r"片段",
    r"文档",
    r"资料中",
    r"根据.{0,12}(指南|规范|方案|共识)",
]

CJK_RE = re.compile(r"[\u3400-\u9fff]")
PUNCT_SPLIT_RE = re.compile(r"[。；！？：\n]")


def _norm_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower().replace(" ", "")


def _strip_title(value: str) -> str:
    return re.sub(r"[《》【】\s：:：·、，,。.（）()\-—_]", "", value or "")


def _bigrams(value: str) -> set[str]:
    clean = re.sub(r"\s+", "", value)
    return {clean[i : i + 2] for i in range(len(clean) - 1)} if len(clean) > 1 else {clean}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_corpus() -> tuple[dict[str, dict], list[dict]]:
    settings = get_settings()
    active_path, active_version = _resolve_active(settings)
    chunks = []
    with (active_path / "chunks.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    docs = {}
    with (REPO_ROOT / "RAG" / "corpus_manifest.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                doc = json.loads(line)
                docs[doc["doc_id"]] = doc
    return docs, chunks


def _resolve_active(settings):
    from app.rag.index_versions import resolve_active_index

    return resolve_active_index(settings.rag_index_dir)


def eligible_chunks(docs: dict[str, dict], chunks: list[dict]) -> list[dict]:
    out = []
    for chunk in chunks:
        doc = docs.get(chunk.get("parent_doc_id") or "")
        if doc is None:
            continue
        if doc.get("review_status") == "needs_review":
            continue
        if doc.get("source_type") in {"incomplete_preview", "download_placeholder"}:
            continue
        title = doc.get("title") or ""
        if any(bad in title for bad in DOC_TITLE_BLACKLIST):
            continue
        if chunk.get("is_superseded"):
            continue
        text = chunk.get("text") or ""
        if not 120 <= len(text) <= 1200:
            continue
        cjk = len(CJK_RE.findall(text))
        # Chinese-language public-facing content only; mostly-English paper
        # chunks cannot support natural Chinese public questions.
        if cjk < min(0.25 * len(text), 80):
            continue
        if len(PUNCT_SPLIT_RE.findall(text)) < 4:
            continue  # likely a table of contents / heading list
        out.append(chunk)
    return out


def select_seeds(chunks: list[dict]) -> list[tuple[dict, list[str]]]:
    """Assign difficulty quotas BEFORE any retrieval. Returns [(chunk, [difficulties])]."""
    pool = sorted(
        chunks,
        key=lambda c: (
            DOC_PRIORITY.get(c["corpus_source_type"], 3),
            c["parent_doc_id"],
            c.get("section") or "",
            c["chunk_index"],
        ),
    )
    total = len(pool) * QUESTIONS_PER_CHUNK
    difficulties = (
        ["easy"] * round(total * 0.55)
        + ["medium"] * round(total * 0.35)
        + ["hard"] * (total - round(total * 0.55) - round(total * 0.35))
    )
    random.Random(FREEZE_SEED).shuffle(difficulties)
    seeds = []
    for index, chunk in enumerate(pool):
        start = index * QUESTIONS_PER_CHUNK
        seeds.append((chunk, difficulties[start : start + QUESTIONS_PER_CHUNK]))
    return seeds


def _client():
    from openai import AsyncOpenAI

    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("dashscope_api_key is not configured; cannot run generation")
    return AsyncOpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        timeout=120,
        max_retries=0,
    )


GENERATION_PROMPT = """你是疫苗科普评测题库的构建助手。下面给出本地疫苗知识库的一个知识片段（含所属章节，仅供你理解上下文）。

【片段内容】
{chunk_text}

【所属章节】{section}

请围绕该片段中 {n} 个互不相同、明确、稳定、可核对的核心事实，生成 {n} 个公众自然问题。每个问题只针对一个核心事实，问题之间不得问同一件事。

难度要求（每个问题的难度按 difficulties 列表逐一对应）：
- easy：单一核心事实，常见公众问法，与片段表达可以有适度的自然关键词重合。
- medium：对原文表达做自然改写或换一种问法，或"一个生活场景/一个条件 + 一个核心事实"，需要一定语义理解，但答案仍能从片段直接读出。
- hard：包含两个条件（如"某疫苗 + 某情况"），或涉及易混淆概念（如两种疫苗、两种反应、两个程序的区分），措辞与片段原文差异较大，公众确实会这样问。

硬性要求：
1. 问题必须是普通公众（家长、接种者）真实会问的口吻，不要出现"根据某规范""文档中""片段"等表述。
2. 问题不得泄露文档标题、文件名、章节编号或片段编号。
3. 每个问题必须能仅凭该片段回答，不得需要片段之外的知识。
4. 不得是个体化临床诊断请求（例如"我家孩子今天能不能打"），要问一般性知识。
5. 问题以问号结尾，长度在 8 到 60 个字符之间。
6. 保留公众自然会使用的核心医学关键词（如 HPV、狂犬疫苗、流感疫苗、补种、发热、过敏、加强针），不要刻意替换掉。

只输出一个合法 JSON 对象，不要输出 Markdown 或其他文字：
{{"items": [{{"question": "...", "core_fact": "片段中支撑该答案的那句核心事实（尽量原文摘录）", "expected_answer": "依据该片段给出的一句话标准答案"}}]}}
其中 difficulties = {difficulties}，items 数量必须等于 {n}，第 i 个 item 的难度就是 difficulties[i]。"""

DIFFICULTY_DESC = {
    "easy": "easy（简单）难度",
    "medium": "medium（中等）难度",
    "hard": "hard（较难）难度",
}


async def generate_one(client, model: str, chunk: dict, difficulties: list[str], sem) -> list[dict] | None:
    prompt = GENERATION_PROMPT.format(
        chunk_text=chunk["text"],
        section=chunk.get("section") or "（无明确章节）",
        n=len(difficulties),
        difficulties=difficulties,
    )
    async with sem:
        for attempt in range(4):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    extra_body={"enable_thinking": False},
                )
                content = response.choices[0].message.content or ""
                content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
                data = json.loads(content)
                items = data.get("items") or []
                results = []
                for offset, item in enumerate(items[: len(difficulties)]):
                    question = str(item.get("question") or "").strip()
                    core_fact = str(item.get("core_fact") or "").strip()
                    expected = str(item.get("expected_answer") or "").strip()
                    if not question or not expected:
                        continue
                    results.append(
                        {
                            "seed_chunk_id": chunk["id"],
                            "doc_id": chunk["parent_doc_id"],
                            "section": chunk.get("section"),
                            "difficulty": difficulties[min(offset, len(difficulties) - 1)],
                            "question": question,
                            "core_fact": core_fact,
                            "expected_answer": expected,
                        }
                    )
                if len(results) >= max(1, len(difficulties) - 1):
                    return results
                raise ValueError(f"only {len(results)}/{len(difficulties)} questions returned")
            except Exception:
                await asyncio.sleep(2.0 * (attempt + 1))
        return None


async def run_generation(seeds: list[tuple[dict, list[str]]]) -> None:
    client = _client()
    model = get_settings().qwen_model
    sem = asyncio.Semaphore(8)
    tasks = [generate_one(client, model, chunk, diffs, sem) for chunk, diffs in seeds]
    results: list[list[dict] | None] = []
    done = 0
    for fut in asyncio.as_completed(tasks):
        results.append(await fut)
        done += 1
        if done % 25 == 0:
            print(f"[generate] chunks {done}/{len(tasks)}", flush=True)
    ok = [r for r in results if r is not None]
    failed = len(results) - len(ok)
    print(f"[generate] chunk success={len(ok)} failed={failed}")
    if failed:
        missing = [seeds[i] for i, r in enumerate(results) if r is None]
        print(f"[generate] retrying {len(missing)} failed chunks sequentially")
        retry = [await generate_one(client, model, chunk, diffs, asyncio.Semaphore(4)) for chunk, diffs in missing]
        ok.extend(r for r in retry if r is not None)
        print(f"[generate] after retry chunk success={len(ok)}")
    candidates = [item for group in ok for item in group]
    with CANDIDATES_RAW.open("w", encoding="utf-8") as fh:
        for item in candidates:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"[generate] wrote {len(candidates)} -> {CANDIDATES_RAW}")


def rule_screen(candidates: list[dict], docs: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    excluded: list[dict] = []
    kept_norms: list[str] = []
    kept_bigrams: list[set[str]] = []
    title_norms: dict[str, str] = {}

    for order, cand in enumerate(candidates):
        case_key = f"cand-{order:04d}"
        doc = docs.get(cand["doc_id"], {})
        title_norm = title_norms.setdefault(cand["doc_id"], _strip_title(doc.get("title") or ""))
        question = cand["question"].strip()

        def exclude(reason_code: str, reason: str):
            excluded.append(
                {
                    "candidate_key": case_key,
                    "question": question,
                    "seed_chunk_id": cand["seed_chunk_id"],
                    "doc_id": cand["doc_id"],
                    "difficulty": cand["difficulty"],
                    "stage": "rule",
                    "reason_code": reason_code,
                    "reason": reason,
                }
            )

        if not 8 <= len(question) <= 100:
            exclude("bad_length", "问题长度不符合公众提问范围（8-100 字符）")
            continue
        if not question.endswith(("？", "?")):
            exclude("not_question", "问题不是以问号结尾的提问形式")
            continue
        if any(re.search(p, question) for p in BANNED_QUESTION_PATTERNS):
            exclude("references_source", "问题引用了文件、文档或知识库表述，泄露评测构造方式")
            continue
        if len(title_norm) >= 6 and title_norm in _strip_title(question):
            exclude("leaks_title", "问题包含文档标题，泄露来源信息")
            continue

        q_norm = _norm_text(question)
        q_bigrams = _bigrams(q_norm)
        duplicate = False
        for prev_norm, prev_bigrams in zip(kept_norms, kept_bigrams):
            if difflib.SequenceMatcher(None, q_norm, prev_norm).ratio() >= 0.85:
                duplicate = True
                break
            if _jaccard(q_bigrams, prev_bigrams) >= 0.9:
                duplicate = True
                break
        if duplicate:
            exclude("duplicate", "与已保留候选问题重复或近似重复")
            continue

        # Same-document near-identical expected answers are treated as duplicates.
        ans_norm = _norm_text(cand["expected_answer"])
        for prev in kept:
            if prev["doc_id"] != cand["doc_id"]:
                continue
            if difflib.SequenceMatcher(None, ans_norm, _norm_text(prev["expected_answer"])).ratio() >= 0.92:
                duplicate = True
                break
        if duplicate:
            exclude("duplicate", "同文档内核心答案重复")
            continue

        kept.append({**cand, "candidate_key": case_key, "order": order})
        kept_norms.append(q_norm)
        kept_bigrams.append(q_bigrams)
    return kept, excluded


SCREEN_PROMPT = """你是疫苗科普评测题库的质量筛查员。对下面每条候选问题，依据给定的知识片段（gold）判断是否可以保留为正式检索评测题。

判断标准（必须全部满足才保留）：
A. gold 片段能够直接支撑问题的核心答案，不需要读者做复杂推理；
B. 问题只有一个明确答案，gold 片段内部或可见信息不会给出互相冲突的答案；
C. 问题只需要库内知识，不需要实时信息、外部数据库或片段之外的医学知识；
D. 问题语义清晰，不存在严重歧义（不会同时指两种完全不同的理解）；
E. 问题属于面向公众的疫苗科普范围，不是过于冷门的专业细节；
F. 问题不要求对具体个人做临床决策判断；
G. 问题不需要综合多个文档推理（gold 单片段就能回答）。

对每条输出一行 JSON：{{"key": "...", "verdict": "keep"|"exclude", "reason_code": "...", "reason": "..."}}
reason_code 只能取：gold_unclear / conflicting_answers / needs_outside_knowledge / ambiguous_question / poor_gold_quality / too_obscure / individualized_clinical / multi_doc_reasoning。
保留时 reason 写 "ok"。

【候选列表】
{items}"""


def _format_items(batch: list[dict]) -> str:
    lines = []
    for item in batch:
        chunk_text = item.get("_chunk_text", "")
        lines.append(
            f'- key: {item["candidate_key"]}\n'
            f"  问题: {item['question']}\n"
            f"  期望答案: {item['expected_answer']}\n"
            f"  gold片段: {chunk_text}"
        )
    return "\n".join(lines)


async def llm_screen(client, model: str, kept: list[dict], docs: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    chunk_texts = {}
    _, chunks = load_corpus()
    for chunk in chunks:
        chunk_texts[chunk["id"]] = chunk["text"]
    for item in kept:
        item["_chunk_text"] = chunk_texts.get(item["seed_chunk_id"], "")

    passed: list[dict] = []
    excluded: list[dict] = []
    sem = asyncio.Semaphore(6)

    async def screen_batch(batch: list[dict]):
        async with sem:
            for attempt in range(4):
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "user",
                                "content": SCREEN_PROMPT.format(items=_format_items(batch)),
                            }
                        ],
                        temperature=0.0,
                        extra_body={"enable_thinking": False},
                    )
                    content = response.choices[0].message.content or ""
                    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
                    # Model may wrap the list in a JSON array.
                    if content.startswith("["):
                        verdicts = json.loads(content)
                    else:
                        verdicts = [json.loads(m) for m in re.findall(r"\{[^{}]*\}", content, flags=re.S)]
                    return batch, verdicts
                except Exception:
                    await asyncio.sleep(3.0 * (attempt + 1))
            return batch, None

    batches = [kept[i : i + 8] for i in range(0, len(kept), 8)]
    results = []
    done = 0
    for fut in asyncio.as_completed([screen_batch(b) for b in batches]):
        results.append(await fut)
        done += 1
        if done % 10 == 0:
            print(f"[screen] {done}/{len(batches)} batches", flush=True)

    verdict_map: dict[str, dict] = {}
    failed_batches = []
    for batch, verdicts in results:
        if verdicts is None:
            failed_batches.append(batch)
            continue
        for verdict in verdicts:
            key = str(verdict.get("key") or "")
            if key:
                verdict_map[key] = verdict
    if failed_batches:
        flat = [item for batch in failed_batches for item in batch]
        print(f"[screen] retrying {len(failed_batches)} failed batches sequentially")
        retry_results = [await screen_batch(b) for b in [flat[i : i + 8] for i in range(0, len(flat), 8)]]
        for batch, verdicts in retry_results:
            if verdicts is None:
                continue
            for verdict in verdicts:
                key = str(verdict.get("key") or "")
                if key:
                    verdict_map[key] = verdict

    for item in kept:
        verdict = verdict_map.get(item["candidate_key"])
        record = {
            "candidate_key": item["candidate_key"],
            "question": item["question"],
            "seed_chunk_id": item["seed_chunk_id"],
            "doc_id": item["doc_id"],
            "difficulty": item["difficulty"],
            "stage": "llm",
            "verdict": (verdict or {}).get("verdict", "no_verdict"),
            "reason_code": (verdict or {}).get("reason_code"),
            "reason": (verdict or {}).get("reason"),
        }
        if verdict is not None and verdict.get("verdict") == "keep":
            passed.append(item)
        else:
            excluded.append(record)
    return passed, excluded


def select_final(passed: list[dict], docs: dict[str, dict]) -> list[dict]:
    """Deterministically select 1000 cases under frozen quotas. Blind to retrieval."""
    by_diff: dict[str, list[dict]] = defaultdict(list)
    for item in passed:
        by_diff[item["difficulty"]].append(item)

    selected: list[dict] = []
    doc_count: Counter = Counter()
    doc_type = {
        doc_id: (
            docs[doc_id]["source_type"]
            if doc_id in docs
            else "academic_paper"
        )
        for doc_id in {item["doc_id"] for item in passed}
    }

    for diff in ("easy", "medium", "hard"):
        pool = by_diff.get(diff, [])
        # Round-robin across documents to spread coverage, stable within doc by order.
        by_doc: dict[str, list[dict]] = defaultdict(list)
        for item in sorted(pool, key=lambda x: x["order"]):
            by_doc[item["doc_id"]].append(item)
        doc_cycle = sorted(
            by_doc,
            key=lambda d: (
                DOC_PRIORITY.get(doc_type.get(d, "academic_paper"), 3),
                sum(1 for s in selected if s["doc_id"] == d),
                d,
            ),
        )
        quota = FINAL_QUOTAS[diff]
        progress = True
        while len([s for s in selected if s["difficulty"] == diff]) < quota and progress:
            progress = False
            for doc_id in doc_cycle:
                if len([s for s in selected if s["difficulty"] == diff]) >= quota:
                    break
                items = by_doc.get(doc_id)
                if not items:
                    continue
                cap = FINAL_DOC_CAPS.get(doc_type.get(doc_id, "academic_paper"), 100)
                if doc_count[doc_id] >= cap:
                    continue
                item = items.pop(0)
                selected.append(item)
                doc_count[doc_id] += 1
                progress = True
    return selected


def expand_acceptable_gold(cases: list[dict], chunks_by_doc: dict[str, list[dict]]) -> None:
    for case in cases:
        seed = chunks_by_doc[case["doc_id"]]
        primary = next(c for c in seed if c["id"] == case["seed_chunk_id"])
        seed_bigrams = _bigrams(primary["text"])
        acceptable = [primary["id"]]
        for chunk in seed:
            if chunk["id"] == primary["id"]:
                continue
            jaccard = _jaccard(_bigrams(chunk["text"]), seed_bigrams)
            if jaccard < 0.45:
                continue
            if difflib.SequenceMatcher(None, chunk["text"], primary["text"]).ratio() >= 0.5:
                acceptable.append(chunk["id"])
        case["acceptable_gold_chunk_ids"] = acceptable[:8]


def freeze(passed: list[dict], docs: dict[str, dict], chunks_by_doc: dict[str, list[dict]]) -> None:
    selected = select_final(passed, docs)
    if len(selected) != FINAL_TOTAL:
        counts = Counter(s["difficulty"] for s in selected)
        raise SystemExit(
            f"selection produced {len(selected)} cases (need {FINAL_TOTAL}); "
            f"difficulty counts: {dict(counts)}. Add more candidates before freezing."
        )
    expand_acceptable_gold(selected, chunks_by_doc)

    # Stable final ordering: category, difficulty, generation order.
    def category(item: dict) -> str:
        doc = docs.get(item["doc_id"], {})
        rel = doc.get("relative_path") or ""
        return rel.replace("\\", "/").split("/")[0] if "/" in rel or "\\" in rel else rel

    selected.sort(key=lambda s: (category(s), ["easy", "medium", "hard"].index(s["difficulty"]), s["order"]))

    with CASES_PATH.open("w", encoding="utf-8") as fh, GOLD_PATH.open("w", encoding="utf-8") as gold_fh:
        for index, item in enumerate(selected, start=1):
            case_id = f"RAGV2-{index:04d}"
            doc = docs.get(item["doc_id"], {})
            cat = category(item)
            fh.write(
                json.dumps(
                    {
                        "case_id": case_id,
                        "question": item["question"],
                        "category": cat,
                        "difficulty": item["difficulty"],
                        "gold_source_ids": [item["doc_id"]],
                        "gold_chunk_ids": [item["seed_chunk_id"]],
                        "acceptable_gold_chunk_ids": item["acceptable_gold_chunk_ids"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            gold_fh.write(
                json.dumps(
                    {
                        "case_id": case_id,
                        "question": item["question"],
                        "category": cat,
                        "difficulty": item["difficulty"],
                        "seed_chunk_id": item["seed_chunk_id"],
                        "acceptable_gold_chunk_ids": item["acceptable_gold_chunk_ids"],
                        "gold_source_ids": [item["doc_id"]],
                        "document_title": doc.get("title"),
                        "file_name": doc.get("filename"),
                        "section": item.get("section") or doc.get("topic"),
                        "core_fact": item["core_fact"],
                        "expected_answer": item["expected_answer"],
                        "llm_screen": item.get("llm_screen", "keep"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"[freeze] wrote {len(selected)} cases -> {CASES_PATH}")


TOPUP_PROMPT = """你是疫苗科普评测题库的构建助手。下面给出本地疫苗知识库的一个知识片段，以及已经基于该片段生成过的问题列表。

【片段内容】
{chunk_text}

【已生成的问题】
{existing}

请再围绕该片段中 {n} 个互不相同、明确、稳定、可核对的核心事实，生成 {n} 个新的公众自然问题。
要求：
1. 新问题的事实角度必须与已生成的问题明显不同，不得重复或换一种问法重复。
2. 其余要求与之前一致：公众口吻、不泄露文档标题/文件名/章节编号、仅凭该片段可答、非个体化临床诊断、问号结尾、8-60 字符。
3. 难度按 difficulties 列表逐一对应：easy=常见问法可含自然关键词重合；medium=自然改写或一个条件+一个核心事实；hard=两个条件或易混淆概念、措辞与原文差异较大。

只输出一个合法 JSON 对象：
{{"items": [{{"question": "...", "core_fact": "片段中支撑该答案的那句核心事实（尽量原文摘录）", "expected_answer": "依据该片段给出的一句话标准答案"}}]}}
其中 difficulties = {difficulties}，items 数量必须等于 {n}。"""


async def run_topup(docs: dict[str, dict], chunks_by_doc: dict[str, list[dict]]) -> None:
    chunk_by_id = {c["id"]: c for group in chunks_by_doc.values() for c in group}
    existing_raw = [json.loads(line) for line in CANDIDATES_RAW.open(encoding="utf-8") if line.strip()]
    by_chunk: dict[str, list[dict]] = defaultdict(list)
    for item in existing_raw:
        by_chunk[item["seed_chunk_id"]].append(item)

    total = len(by_chunk) * 2
    difficulties = (
        ["easy"] * round(total * 0.55)
        + ["medium"] * round(total * 0.35)
        + ["hard"] * (total - round(total * 0.55) - round(total * 0.35))
    )
    random.Random(FREEZE_SEED + 1).shuffle(difficulties)

    client = _client()
    model = get_settings().qwen_model
    sem = asyncio.Semaphore(8)

    async def topup_one(index: int, chunk_id: str):
        chunk = chunk_by_id[chunk_id]
        existing = "\n".join(
            f"{i + 1}. {item['question']}" for i, item in enumerate(by_chunk[chunk_id])
        )
        diffs = difficulties[index * 2 : index * 2 + 2]
        prompt = TOPUP_PROMPT.format(
            chunk_text=chunk["text"],
            existing=existing,
            n=len(diffs),
            difficulties=diffs,
        )
        async with sem:
            for attempt in range(4):
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7,
                        extra_body={"enable_thinking": False},
                    )
                    content = response.choices[0].message.content or ""
                    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
                    data = json.loads(content)
                    items = data.get("items") or []
                    results = []
                    for offset, item in enumerate(items[: len(diffs)]):
                        question = str(item.get("question") or "").strip()
                        core_fact = str(item.get("core_fact") or "").strip()
                        expected = str(item.get("expected_answer") or "").strip()
                        if not question or not expected:
                            continue
                        results.append(
                            {
                                "seed_chunk_id": chunk["id"],
                                "doc_id": chunk["parent_doc_id"],
                                "section": chunk.get("section"),
                                "difficulty": diffs[min(offset, len(diffs) - 1)],
                                "question": question,
                                "core_fact": core_fact,
                                "expected_answer": expected,
                            }
                        )
                    if results:
                        return results
                    raise ValueError("empty results")
                except Exception:
                    await asyncio.sleep(2.0 * (attempt + 1))
            return []

    tasks = [topup_one(i, chunk_id) for i, chunk_id in enumerate(sorted(by_chunk))]
    results = []
    done = 0
    for fut in asyncio.as_completed(tasks):
        results.append(await fut)
        done += 1
        if done % 50 == 0:
            print(f"[topup] {done}/{len(tasks)}", flush=True)
    new_items = [item for group in results for item in group]
    print(f"[topup] new candidates: {len(new_items)}")
    with CANDIDATES_RAW.open("a", encoding="utf-8") as fh:
        for item in new_items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"[topup] total candidates now: {len(existing_raw) + len(new_items)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["generate", "topup", "screen", "select"])
    args = parser.parse_args()

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    docs, chunks = load_corpus()
    chunks_by_doc: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_doc[chunk["parent_doc_id"]].append(chunk)

    if args.stage == "generate":
        seeds = select_seeds(eligible_chunks(docs, chunks))
        print(f"[generate] seed chunks: {len(seeds)}")
        asyncio.run(run_generation(seeds))
        return

    if args.stage == "topup":
        asyncio.run(run_topup(docs, chunks_by_doc))
        return

    if args.stage == "select":
        if not SCREEN_RESULTS.exists():
            raise SystemExit("screen results missing; run the screen stage first")
        passed = [json.loads(line) for line in SCREEN_RESULTS.open(encoding="utf-8") if line.strip()]
        print(f"[select] screened pool: {len(passed)}")
        freeze(passed, docs, chunks_by_doc)
        return

    candidates = [json.loads(line) for line in CANDIDATES_RAW.open(encoding="utf-8") if line.strip()]
    print(f"[screen] candidates loaded: {len(candidates)}")
    kept, rule_excluded = rule_screen(candidates, docs)
    print(f"[screen] after rule screen: kept={len(kept)} excluded={len(rule_excluded)}")
    client = _client()
    model = get_settings().qwen_model
    passed, llm_excluded = asyncio.run(llm_screen(client, model, kept, docs))
    for item in passed:
        item["llm_screen"] = "keep"
    print(f"[screen] after LLM screen: kept={len(passed)} excluded={len(llm_excluded)}")

    with SCREEN_RESULTS.open("w", encoding="utf-8") as fh:
        for item in passed:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    with EXCLUSIONS.open("w", encoding="utf-8") as fh:
        for record in rule_excluded + llm_excluded:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"[screen] wrote exclusions: {len(rule_excluded) + len(llm_excluded)} -> {EXCLUSIONS}")


if __name__ == "__main__":
    main()
