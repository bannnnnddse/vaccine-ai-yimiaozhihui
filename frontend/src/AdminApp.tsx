import { ArrowClockwise, BookOpenText, Check, Clock, DownloadSimple, FloppyDisk, LockKey, Plus, SignOut, Trash, X } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  AdminApiError, approveKnowledgeGap, draftDownloadUrl, getKnowledgeDraft, getKnowledgeGap,
  getGraphJob, getPublicGraphMeta, holdKnowledgeGap, listKnowledgeGaps, loginAdmin, logoutAdmin, publishKnowledgeGap,
  rebuildKnowledgeGraph,
  rejectKnowledgeGap, restoreAdminSession, saveKnowledgeGapReview,
  type CandidateClaim, type DraftPreview, type GapDetail, type GapStatus, type GraphJob, type KnowledgeGap,
} from "./services/adminService";
import { AdminHomeLink } from "./components/AdminHomeLink";
import "./admin.css";

const statusLabels: Record<GapStatus, string> = {
  pending: "待审核", in_review: "审核中", hold: "暂缓", approved: "待发布", publishing: "发布中", rejected: "已拒绝", published: "已发布",
};
const eventLabels: Record<string, string> = {
  created: "系统创建缺口", review_saved: "保存审核", held: "暂缓审核", approved: "批准候选",
  rejected: "拒绝候选", publish_queued: "进入发布队列", publish_failed: "发布失败并回滚", published: "发布到知识库",
};

export function AdminApp() {
  const [session, setSession] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => { restoreAdminSession().then((value) => setSession(value.username)).catch(() => undefined).finally(() => setChecking(false)); }, []);
  if (checking) return <div className="admin-boot">正在核验管理会话…</div>;
  if (!session) return <AdminLogin onLogin={setSession} />;
  return <ReviewWorkspace username={session} onLogout={() => setSession(null)} />;
}

function AdminLogin({ onLogin }: { onLogin: (username: string) => void }) {
  const [username, setUsername] = useState(""); const [password, setPassword] = useState("");
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { const value = await loginAdmin(username, password); onLogin(value.username); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "登录失败"); }
    finally { setBusy(false); }
  };
  return <main className="admin-login">
    <section className="admin-login__story" aria-hidden="true">
      <span className="admin-kicker">EVIDENCE DESK · 证据审核台</span>
      <h1>把未知，<br />变成可追溯的知识。</h1>
      <p>内部证据、PubMed 文献与人工判断在这里汇合。只有经过明确批准和发布的主张，才会进入知识库。</p>
    </section>
    <form className="admin-login__card" onSubmit={submit}>
      <LockKey size={34} weight="duotone" aria-hidden="true" />
      <div><span>受控入口</span><h2>管理员登录</h2></div>
      <label>用户名<input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
      <label>密码<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      {error && <p className="admin-error" role="alert">{error}</p>}
      <button className="admin-primary" disabled={busy}>{busy ? "正在验证…" : "进入审核台"}</button>
      <AdminHomeLink className="admin-login__home" />
      <small>主站保持匿名开放；此入口仅用于知识审核与发布。</small>
    </form>
  </main>;
}

function ReviewWorkspace({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [items, setItems] = useState<KnowledgeGap[]>([]); const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<GapStatus | "">(""); const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<GapDetail | null>(null); const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const refresh = async () => { setLoading(true); setError(""); try { const result = await listKnowledgeGaps(status, query); setItems(result.items); setTotal(result.total); } catch (reason) { handleError(reason, setError, onLogout); } finally { setLoading(false); } };
  useEffect(() => { void refresh(); }, [status]);
  const open = async (id: string) => { setError(""); try { setSelected(await getKnowledgeGap(id)); } catch (reason) { handleError(reason, setError, onLogout); } };
  return <main className="review-shell">
    <header className="review-header"><div><span className="admin-kicker">VACCINE KNOWLEDGE · CONTROL ROOM</span><h1>KnowledgeGap 审核台</h1></div><div className="review-header__actions"><span>{username}</span><AdminHomeLink /><button onClick={() => logoutAdmin().finally(onLogout)}><SignOut />退出</button></div></header>
    <section className="review-toolbar">
      <div className="review-count"><strong>{total}</strong><span>条知识缺口</span></div>
      <div className="status-tabs">{(["", "pending", "in_review", "hold", "approved", "publishing", "rejected", "published"] as const).map((value) => <button className={status === value ? "is-active" : ""} onClick={() => setStatus(value)} key={value || "all"}>{value ? statusLabels[value] : "全部"}</button>)}</div>
      <form onSubmit={(event) => { event.preventDefault(); void refresh(); }}><input aria-label="搜索知识缺口" placeholder="搜索问题或判定原因" value={query} onChange={(e) => setQuery(e.target.value)} /><button><ArrowClockwise />检索</button></form>
    </section>
    <GraphBuildPanel />
    {error && <p className="admin-error review-alert" role="alert">{error}</p>}
    <section className="review-board">
      <aside className="gap-list" aria-busy={loading}>{items.length === 0 && !loading ? <p className="empty-copy">当前筛选下没有知识缺口。</p> : items.map((gap) => <button key={gap.id} className={`gap-card${selected?.gap.id === gap.id ? " is-selected" : ""}`} onClick={() => void open(gap.id)}><span className={`status-mark status-${gap.status}`}>{statusLabels[gap.status]}</span><strong>{gap.original_query}</strong><p>{gap.assessment_reason}</p><time>{formatDate(gap.created_at)}</time></button>)}</aside>
      <section className="gap-detail">{selected ? <GapReviewer key={`${selected.gap.id}-${selected.gap.version}`} detail={selected} onChanged={(next) => { setSelected(next); void refresh(); }} onExpired={onLogout} /> : <div className="detail-empty"><BookOpenText size={58} weight="thin" /><h2>选择一条知识缺口</h2><p>查看当轮内部证据、PubMed 补证和完整审核轨迹。</p></div>}</section>
    </section>
  </main>;
}

function GapReviewer({ detail, onChanged, onExpired }: { detail: GapDetail; onChanged: (value: GapDetail) => void; onExpired: () => void }) {
  const { gap } = detail; const [claims, setClaims] = useState<CandidateClaim[]>(gap.candidate_claims);
  const [note, setNote] = useState(gap.reviewer_note ?? ""); const [title, setTitle] = useState(gap.rewritten_query);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(""); const [draft, setDraft] = useState<DraftPreview | null>(null);
  const [publishJob, setPublishJob] = useState<GraphJob | null>(null);
  const mountedRef = useRef(true);
  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; }; }, []);
  const editable = ["pending", "in_review", "hold"].includes(gap.status);
  useEffect(() => { if (gap.status === "approved" || gap.status === "published") getKnowledgeDraft(gap.id).then(setDraft).catch((reason) => handleError(reason, setError, onExpired)); }, [gap.id, gap.status]);
  const action = async (name: string, run: () => Promise<GapDetail>) => { setBusy(name); setError(""); try { onChanged(await run()); } catch (reason) { handleError(reason, setError, onExpired); } finally { setBusy(""); } };
  const addClaim = () => setClaims((current) => [...current, { text: "", evidence_pmids: [] }]);
  const startPublish = async () => {
    setBusy("publish"); setError("");
    try {
      let job = await publishKnowledgeGap(gap.id, gap.version); setPublishJob(job);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 1600));
        if (!mountedRef.current) return;
        job = await getGraphJob(job.task_id); setPublishJob(job);
      }
      if (job.status === "failed") throw new Error(job.error || "发布任务失败，知识库仍保持旧版本。");
      onChanged(await getKnowledgeGap(gap.id));
    } catch (reason) { handleError(reason, setError, onExpired); }
    finally { setBusy(""); }
  };
  const updateClaim = (index: number, next: CandidateClaim) => setClaims((current) => current.map((item, i) => i === index ? next : item));
  return <article className="review-document">
    <header className="document-head"><div><span className={`status-mark status-${gap.status}`}>{statusLabels[gap.status]}</span><span>版本 {gap.version}</span></div><h2>{gap.original_query}</h2><p>检索改写：{gap.rewritten_query}</p></header>
    {error && <p className="admin-error" role="alert">{error}</p>}
    <section className="evidence-summary"><div><span>评估</span><strong>{gap.assessment_status}</strong></div><div><span>判定原因</span><p>{gap.assessment_reason}</p></div><div><span>缺失方面</span><p>{gap.missing_aspects.join(" · ") || "未记录"}</p></div><div><span>触发原因</span><p>{gap.trigger_reason}</p></div></section>
    <EvidenceSection title={`内部 RAG 证据 · ${gap.internal_evidence.length}`}>{gap.internal_evidence.map((item, index) => <article className="evidence-card" key={`${item.file_name}-${index}`}><div><strong>{item.source_title || item.file_name}</strong><span>{item.page ? `第 ${item.page} 页` : item.section || item.source_type || "来源"}</span></div><p>{item.excerpt}</p><small>相似度 {(item.similarity * 100).toFixed(1)}%</small>{item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">查看原文</a>}</article>)}</EvidenceSection>
    <EvidenceSection title={`PubMed 外部证据 · ${gap.pubmed_evidence.length}`}>{gap.pubmed_evidence.map((item) => <article className="pubmed-card" key={item.pmid}><div><span>PMID {item.pmid}</span><a href={item.url} target="_blank" rel="noreferrer">打开 PubMed ↗</a></div><h3>{item.title}</h3><p>{item.abstract_excerpt || "该记录未返回摘要。"}</p><footer>{[item.journal, item.year, item.doi && `DOI ${item.doi}`].filter(Boolean).join(" · ")}</footer></article>)}</EvidenceSection>
    <section className="claim-editor"><div className="section-title"><div><span>03</span><h3>候选知识主张</h3></div>{editable && <button onClick={addClaim}><Plus />增加主张</button>}</div>{claims.length === 0 && <p className="empty-copy">尚未整理 CandidateClaim。先依据证据写出可独立核验的知识主张。</p>}{claims.map((claim, index) => <article className="claim-card" key={index}><header><strong>主张 {String(index + 1).padStart(2, "0")}</strong>{editable && <button aria-label={`删除主张 ${index + 1}`} onClick={() => setClaims((current) => current.filter((_, i) => i !== index))}><Trash /></button>}</header><textarea disabled={!editable} value={claim.text} onChange={(e) => updateClaim(index, { ...claim, text: e.target.value })} placeholder="输入经人工确认、可进入知识库的完整主张" /><fieldset disabled={!editable}><legend>绑定证据</legend>{gap.pubmed_pmids.map((pmid) => <label key={pmid}><input type="checkbox" checked={claim.evidence_pmids.includes(pmid)} onChange={(e) => updateClaim(index, { ...claim, evidence_pmids: e.target.checked ? [...claim.evidence_pmids, pmid] : claim.evidence_pmids.filter((value) => value !== pmid) })} />PMID {pmid}</label>)}</fieldset></article>)}</section>
    {editable && <section className="review-form"><label>最终候选标题<input value={title} onChange={(e) => setTitle(e.target.value)} /></label><label>审核说明<textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="记录证据判断、限制和发布注意事项" /></label><div className="decision-row"><button disabled={Boolean(busy)} onClick={() => void action("save", () => saveKnowledgeGapReview(gap.id, gap.version, note, claims))}><FloppyDisk />{busy === "save" ? "保存中…" : "保存审核"}</button>{gap.status === "in_review" && <><button disabled={Boolean(busy) || !note.trim()} onClick={() => void action("hold", () => holdKnowledgeGap(gap.id, gap.version, note))}><Clock />暂缓</button><button className="danger" disabled={Boolean(busy) || !note.trim()} onClick={() => window.confirm("确认拒绝这条候选？") && void action("reject", () => rejectKnowledgeGap(gap.id, gap.version, note))}><X />拒绝</button><button className="approve" disabled={Boolean(busy) || !note.trim() || claims.length === 0} onClick={() => void action("approve", () => approveKnowledgeGap(gap.id, gap.version, title, note, claims))}><Check />批准并生成草稿</button></>}</div></section>}
    {publishJob && <p className="graph-job-progress" aria-live="polite">图谱同步 · {publishJob.stage} · {Math.round(publishJob.progress * 100)}%</p>}
    {draft && <DraftPanel gap={gap} draft={draft} busy={busy} onPublish={() => void startPublish()} />}
    <EvidenceSection title="审计历史">{detail.audit_events.map((event) => <div className="audit-row" key={event.id}><span>{eventLabels[event.event_type] || event.event_type}</span><strong>{event.actor}</strong><time>{formatDate(event.created_at)}</time></div>)}</EvidenceSection>
  </article>;
}

function DraftPanel({ gap, draft, busy, onPublish }: { gap: KnowledgeGap; draft: DraftPreview; busy: string; onPublish: () => void }) {
  const [raw, setRaw] = useState(false); const digest = useMemo(() => `${draft.sha256.slice(0, 12)}…${draft.sha256.slice(-8)}`, [draft.sha256]);
  return <section className="draft-panel"><header><div><span>FINAL MARKDOWN</span><h3>实际发布文件预览</h3><small>SHA-256 {digest} · {formatDate(draft.generated_at)}</small></div><div><button onClick={() => setRaw((value) => !value)}>{raw ? "渲染预览" : "查看原文"}</button><a href={draftDownloadUrl(gap.id)}><DownloadSimple />下载</a></div></header><div className={raw ? "markdown-raw" : "markdown-preview"}>{raw ? <pre>{draft.content}</pre> : <ReactMarkdown>{draft.content}</ReactMarkdown>}</div>{gap.status === "approved" && <footer><p>发布将把上方同一份文件写入正式 RAG，并同步重建现有索引。</p><button className="publish" disabled={Boolean(busy)} onClick={() => window.confirm("确认发布到正式知识库并重建索引？该操作可能需要数分钟。") && onPublish()}><BookOpenText />{busy === "publish" ? "正在发布并重建索引…" : "发布到知识库"}</button></footer>}</section>;
}

function EvidenceSection({ title, children }: { title: string; children: React.ReactNode }) { return <section className="evidence-section"><div className="section-title"><div><span>•</span><h3>{title}</h3></div></div><div className="evidence-stack">{children}</div></section>; }

function GraphBuildPanel() {
  const [meta, setMeta] = useState<{ version: string; updated_at: string; node_count: number; edge_count: number; knowledge_base_version: string } | null>(null);
  const [job, setJob] = useState<GraphJob | null>(null); const [error, setError] = useState("");
  const [mode, setMode] = useState<"incremental" | "full">("incremental");
  const [force, setForce] = useState(false);
  const mountedRef = useRef(true);
  const refresh = () => getPublicGraphMeta().then(setMeta).catch(() => setMeta(null));
  useEffect(() => { mountedRef.current = true; void refresh(); return () => { mountedRef.current = false; }; }, []);
  const rebuild = async () => { setError(""); try { let next = await rebuildKnowledgeGraph(mode, force); setJob(next); while (next.status === "queued" || next.status === "running") { await new Promise((resolve) => window.setTimeout(resolve, 1600)); if (!mountedRef.current) return; next = await getGraphJob(next.task_id); setJob(next); } if (next.status === "failed") throw new Error(next.error || "图谱重建失败"); await refresh(); } catch (reason) { if (mountedRef.current) setError(reason instanceof Error ? reason.message : "图谱重建失败"); } };
  return <section className="graph-admin-panel"><div><span className="admin-kicker">KNOWLEDGE GRAPH · SNAPSHOT</span><strong>{meta ? `${meta.node_count} 节点 / ${meta.edge_count} 关系` : "尚无可用快照"}</strong><small>{meta ? `${meta.knowledge_base_version} · ${formatDate(meta.updated_at)}` : "需要由独立 Graph Worker 完成首次构建"}</small></div><div>{job && <span>{job.stage} · {Math.round(job.progress * 100)}%</span>}<select aria-label="图谱构建模式" value={mode} onChange={(event) => setMode(event.target.value as "incremental" | "full")}><option value="incremental">增量聚合</option><option value="full">全量聚合</option></select><label><input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} />强制重新抽取</label><a href="/#graph">打开公共图谱 ↗</a><button onClick={() => void rebuild()} disabled={job?.status === "queued" || job?.status === "running"}><ArrowClockwise />{job?.status === "queued" || job?.status === "running" ? "构建中" : "重建图谱"}</button></div>{error && <p className="admin-error">{error}</p>}</section>;
}
function formatDate(value: string) { return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function handleError(reason: unknown, setError: (value: string) => void, onExpired: () => void) { if (reason instanceof AdminApiError && reason.status === 401) onExpired(); setError(reason instanceof Error ? reason.message : "操作失败"); }
