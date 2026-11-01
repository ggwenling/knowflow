"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Document, KnowledgeBase, QuestionDetail, QuestionHistory, Source, streamQuestion, User } from "@/lib/api";
import styles from "./workspace.module.css";

type Task = { task_id: string; status: string; failure_code: string | null };
const contractVersion = "0.2.0-draft.10";
const terminal = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const labels: Record<string, string> = {
  QUEUED: "等待处理", RUNNING: "正在建立索引", SUCCEEDED: "已就绪", READY: "已就绪",
  FAILED: "处理失败", CANCELLED: "已取消", PROCESSING: "正在处理",
};

function statusLabel(value: string) { return labels[value] ?? value; }
function formatLabel(value: string) { const format = value.toUpperCase(); return format === "PDF" || format === "MD" ? format : "TXT"; }
function messageOf(error: unknown) { return error instanceof Error ? error.message : "操作未能完成"; }
function ApiModeBanner() {
  const [mode, setMode] = useState("unknown");
  useEffect(() => { fetch("/api/mode", { cache: "no-store" }).then((response) => response.json()).then((body) => setMode(body.mode)).catch(() => undefined); }, []);
  return mode === "synthetic" ? <div className={styles.modeBanner} role="status">合成模型 · 仅用于本地工程验证；不代表真实模型质量或费用</div>
    : mode === "external" ? <div className={styles.modeBanner} role="note">请只上传已获授权的资料。文档片段和问题会发送到当前配置的模型服务。</div>
      : <div className={styles.modeBanner} role="note">模型模式尚未配置。上传前请先确认资料获准使用，并确认模型服务的数据处理范围。</div>;
}

export default function Workspace() {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authError, setAuthError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [selectedBase, setSelectedBase] = useState("");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [history, setHistory] = useState<QuestionHistory[]>([]);
  const [answer, setAnswer] = useState<QuestionDetail | null>(null);
  const [activeQuestion, setActiveQuestion] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const [viewing, setViewing] = useState<{ source: Source; document: Document; url: string | null; text: string | null } | null>(null);
  const [openMenu, setOpenMenu] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const questionViewRef = useRef(0);

  function leaveQuestion() {
    questionViewRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
  }

  const refresh = useCallback(async (baseId: string) => {
    const [documentList, historyList] = await Promise.all([
      api<{ items: Document[] }>(`knowledge-bases/${baseId}/documents?limit=50&offset=0`),
      api<{ items: QuestionHistory[] }>("questions?limit=50&offset=0"),
    ]);
    setDocuments(documentList.items);
    setHistory(historyList.items);
  }, []);

  const loadBases = useCallback(async () => {
    const response = await api<{ items: KnowledgeBase[] }>("knowledge-bases?limit=50&offset=0");
    setBases(response.items);
    setSelectedBase((current) => response.items.find((item) => item.id === current)?.id ?? response.items[0]?.id ?? "");
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const current = await api<User>("me");
        if (!active) return;
        setUser(current);
        const response = await api<{ items: KnowledgeBase[] }>("knowledge-bases?limit=50&offset=0");
        if (!active) return;
        setBases(response.items);
        const chosen = response.items.find((item) => item.id === selectedBase)?.id ?? response.items[0]?.id ?? "";
        setSelectedBase(chosen);
        if (chosen) await refresh(chosen);
      } catch (error) {
        if (active) { setUser(null); setNotice(messageOf(error)); }
      } finally { if (active) setAuthLoading(false); }
    })();
    return () => { active = false; };
  }, [refresh, selectedBase]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const readyDocuments = useMemo(() => documents.filter((document) => document.status === "READY" && document.active_index_version_id), [documents]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setAuthError(""); setBusy(true);
    try {
      await api(`auth/${authMode}`, { method: "POST", body: JSON.stringify({ contract_version: contractVersion, email, password }) });
      setUser(await api<User>("me"));
      await loadBases();
      setPassword("");
    } catch (error) { setAuthError(messageOf(error)); }
    finally { setBusy(false); }
  }

  async function signOut() {
    try { await api("auth/logout", { method: "POST", body: "{}" }); } catch { /* The proxy clears expired sessions too. */ }
    leaveQuestion(); setUser(null); setBases([]); setDocuments([]); setHistory([]); setAnswer(null);
  }

  async function createBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); const name = String(form.get("name") ?? "").trim();
    if (!name) return;
    setWorking(true); setNotice("");
    try {
      await api("knowledge-bases", { method: "POST", body: JSON.stringify({ contract_version: contractVersion, name }) });
      await loadBases();
    } catch (error) { setNotice(messageOf(error)); }
    finally { setWorking(false); }
  }

  async function pollDocument(documentId: string, taskId: string, baseId: string) {
    for (;;) {
      const [document, task] = await Promise.all([
        api<Document>(`documents/${documentId}`),
        api<Task>(`tasks/${taskId}`),
      ]);
      setDocuments((previous) => previous.map((item) => item.id === documentId ? document : item));
      if (terminal.has(task.status)) {
        await refresh(baseId);
        if (task.status !== "SUCCEEDED") setNotice(task.failure_code ?? "索引未能完成；可以检查状态后重建。");
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }

  async function upload(file?: File, updateDocument?: Document) {
    if (!file || !selectedBase) return;
    if (file.size > 8 * 1024 * 1024) { setNotice("文件大小不能超过 8 MiB。"); return; }
    setWorking(true); setNotice("");
    try {
      const form = new FormData(); form.set("file", file);
      const path = updateDocument ? `documents/${updateDocument.id}/contents` : `knowledge-bases/${selectedBase}/documents`;
      const accepted = await api<{ document_id: string; task_id: string }>(path, { method: "POST", body: form });
      if (!updateDocument) setDocuments((previous) => [{ id: accepted.document_id, original_name: file.name, status: "QUEUED", format: file.name.split(".").pop() ?? "", byte_size: file.size }, ...previous]);
      await pollDocument(accepted.document_id, accepted.task_id, selectedBase);
    } catch (error) { setNotice(messageOf(error)); }
    finally { setWorking(false); }
  }

  async function rebuild(document: Document) {
    setWorking(true); setNotice("");
    try {
      const accepted = await api<{ task_id: string }>(`documents/${document.id}/rebuilds`, { method: "POST", body: "{}" });
      await pollDocument(document.id, accepted.task_id, selectedBase);
    } catch (error) { setNotice(messageOf(error)); }
    finally { setWorking(false); }
  }

  async function removeDocument(document: Document) {
    if (!window.confirm(`删除“${document.original_name}”？删除后，新问答和原文来源将无法访问。`)) return;
    setWorking(true); setNotice("");
    try {
      await api(`documents/${document.id}`, { method: "DELETE" });
      setDocuments((previous) => previous.filter((item) => item.id !== document.id));
      if (answer?.sources.some((source) => source.document_id === document.id)) {
        setAnswer(null); setNotice("该文档已删除，相关来源已失效。");
      }
    } catch (error) { setNotice(messageOf(error)); }
    finally { setWorking(false); }
  }

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBase || !draft.trim() || busy) return;
    const question = draft.trim();
    setBusy(true); setActiveQuestion(question); setDraft(""); setAnswer(null); setNotice("");
    const controller = new AbortController(); abortRef.current = controller;
    const questionView = ++questionViewRef.current;
    const isCurrent = () => questionViewRef.current === questionView;
    try {
      const response = await fetch(`/api/v1/knowledge-bases/${selectedBase}/questions/stream`, {
        method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: { "content-type": "application/json", "idempotency-key": crypto.randomUUID() },
        body: JSON.stringify({ question }),
      });
      const detail: QuestionDetail = {
        question_id: "", knowledge_base_id: selectedBase, question, status: "PROCESSING",
        finished_at: null, answer: "", has_answer: null, failure_code: null, sources: [],
      };
      if (!isCurrent()) return;
      setAnswer(detail);
      await streamQuestion(response, (delta) => setAnswer((old) => isCurrent() && old ? { ...old, answer: (old.answer ?? "") + delta } : old),
        (sources) => setAnswer((old) => isCurrent() && old ? { ...old, sources } : old));
      if (!isCurrent()) return;
      setAnswer((old) => isCurrent() && old ? { ...old, status: "SUCCEEDED", finished_at: new Date().toISOString() } : old);
      await refresh(selectedBase).catch((error) => setNotice(messageOf(error)));
    } catch (error) {
      if (!isCurrent()) return;
      const reason = controller.signal.aborted ? "用户停止生成" : messageOf(error);
      setAnswer((old) => isCurrent() && old ? { ...old, status: controller.signal.aborted ? "CANCELLED" : "FAILED", failure_code: reason } : old);
      if (!controller.signal.aborted) setNotice(messageOf(error));
      await api<{ items: QuestionHistory[] }>("questions?limit=50&offset=0").then((result) => setHistory(result.items)).catch(() => undefined);
    } finally { if (isCurrent()) { abortRef.current = null; setBusy(false); } }
  }

  async function cancelQuestion() { abortRef.current?.abort(); setNotice("正在停止请求。若生成已经开始，请在历史记录里确认状态，不会自动重发。"); }

  async function openHistory(item: QuestionHistory) {
    leaveQuestion();
    try {
      await refresh(item.knowledge_base_id);
      setSelectedBase(item.knowledge_base_id);
      setAnswer(await api<QuestionDetail>(`questions/${item.question_id}`));
    }
    catch (error) { setNotice(messageOf(error)); }
  }

  async function deleteHistory(item: QuestionDetail) {
    if (!item.question_id || !window.confirm("删除这条问答记录？此操作无法撤销。")) return;
    try {
      await api(`questions/${item.question_id}`, { method: "DELETE" });
      setAnswer(null);
      if (selectedBase) await refresh(selectedBase);
    } catch (error) { setNotice(messageOf(error)); }
  }

  async function viewSource(source: Source) {
    if (viewing?.url) URL.revokeObjectURL(viewing.url);
    const document = documents.find((item) => item.id === source.document_id);
    if (!document) { setNotice("找不到来源对应的文档。"); return; }
    setViewing({ source, document, url: null, text: null });
    try {
      const currentSource = await api<Source>(`sources/${source.source_id}`);
      if (currentSource.document_id !== source.document_id || currentSource.content_version_id !== source.content_version_id) {
        throw new Error("来源已删除或版本已失效。");
      }
      const response = await fetch(`/api/v1/documents/${document.id}/contents/${source.content_version_id}/file`, { credentials: "same-origin" });
      if (!response.ok) throw new Error("来源已删除或版本已失效。");
      if (response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase() === "application/pdf") {
        const url = URL.createObjectURL(await response.blob());
        setViewing((old) => old ? { ...old, url } : old);
      } else {
        const chars = Array.from(await response.text());
        const { start, end } = source.locator ?? { start: 0, end: 0 };
        const excerpt = start != null && end != null ? chars.slice(start, end).join("") : source.quote ?? "";
        setViewing((old) => old ? { ...old, text: excerpt || source.quote || "未提供定位内容。" } : old);
      }
    } catch (error) { setNotice(messageOf(error)); setViewing(null); }
  }

  function closeViewer() {
    if (viewing?.url) URL.revokeObjectURL(viewing.url);
    setViewing(null);
  }

  if (authLoading) return <main className={styles.loading}>正在检查登录状态…</main>;
  if (!user) return (
    <main className={styles.authPage}>
      <section className={styles.authCard}>
        <div className={styles.brandMark}>K</div><span className={styles.eyebrow}>PERSONAL KNOWLEDGE BASE</span>
        <h1>{authMode === "login" ? "回到你的资料" : "建立个人知识库"}</h1>
        <p>上传研发文档，回答问题时可以回到原文核对。</p>
        <form className={styles.authForm} onSubmit={submitAuth}>
          <label>邮箱<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          <label>密码<input type="password" autoComplete={authMode === "login" ? "current-password" : "new-password"} minLength={12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} /><small>12–128 个字符</small></label>
          {authError && <p className={styles.error} role="alert">{authError}</p>}
          <button className={styles.primary} disabled={busy}>{busy ? "正在处理…" : authMode === "login" ? "登录" : "创建账户"}</button>
        </form>
        <button className={styles.textButton} onClick={() => { setAuthMode(authMode === "login" ? "register" : "login"); setAuthError(""); }}>
          {authMode === "login" ? "还没有账户？创建账户" : "已有账户？返回登录"}
        </button>
        <div className={styles.authNote}>个人知识库 · 单轮问答 · 原文可核验</div>
      </section>
    </main>
  );

  const selectedKnowledgeBase = bases.find((base) => base.id === selectedBase);
  return (
    <main className={styles.appShell}>
      <aside className={styles.sidebar}>
        <a className={styles.brand} href="#"><span className={styles.brandMark}>K</span><span>KnowFlow<small>文档核验工作台</small></span></a>
        <div className={styles.sideLabel}>我的知识库</div>
        <div className={styles.baseList}>{bases.map((base) => <button key={base.id} className={`${styles.baseItem} ${selectedBase === base.id ? styles.activeBase : ""}`} onClick={() => { leaveQuestion(); setSelectedBase(base.id); setAnswer(null); void refresh(base.id).catch((error) => setNotice(messageOf(error))); }}><span className={styles.baseGlyph}>▤</span>{base.name}</button>)}</div>
        {bases.length === 0 && <p className={styles.sideEmpty}>这里还没有知识库。</p>}
        <form className={styles.newBase} onSubmit={createBase}><input aria-label="新知识库名称" name="name" placeholder="新建知识库名称" maxLength={200} /><button aria-label="创建知识库" disabled={working}>＋</button></form>
        <div className={styles.sideLabel}>最近问答</div>
        <div className={styles.historyList}>{history.slice(0, 8).map((item) => <button key={item.question_id} className={styles.historyItem} onClick={() => openHistory(item)}><span>{item.question}</span><small>{statusLabel(item.status)}</small></button>)}</div>
        <div className={styles.account}><span className={styles.avatar}>{user.email.slice(0, 1).toUpperCase()}</span><span className={styles.accountText}>{user.email}<small>个人空间</small></span><button className={styles.textButton} onClick={signOut}>退出</button></div>
      </aside>

      <section className={styles.mainColumn}>
        <header className={styles.topbar}><div><span className={styles.eyebrow}>KNOWLEDGE DESK</span><h1>{selectedKnowledgeBase?.name ?? "开始整理你的资料"}</h1></div><div className={styles.topActions}><span className={styles.readyCount}>{readyDocuments.length} 份资料可用于问答</span><label className={styles.uploadButton}>＋ 上传资料<input type="file" accept=".txt,.md,.pdf" disabled={!selectedBase || working} onChange={(event) => { void upload(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label></div></header>
        <ApiModeBanner />
        {notice && <div className={styles.notice} role="status"><span>{notice}</span><button aria-label="关闭提示" onClick={() => setNotice("")}>×</button></div>}
        <div className={styles.workArea}>
          <div className={styles.chatColumn}>
            <div className={styles.sectionHead}><div><span className={styles.eyebrow}>ASK YOUR DOCUMENTS</span><h2>问答与依据</h2></div><span className={styles.singleTurn}>单轮问答</span></div>
            {answer ? <article className={styles.answerCard}>
              <div className={styles.questionLine}><span className={styles.questionMark}>问</span><p>{answer.question || activeQuestion}</p>{answer.question_id && answer.status !== "PROCESSING" && <button className={styles.deleteQuestion} onClick={() => void deleteHistory(answer)}>删除记录</button>}</div>
              {answer.answer ? <div className={styles.answerText}>{answer.answer}</div> : answer.status === "PROCESSING" ? <div className={styles.generating}><span className={styles.pulse} />正在检索并生成回答…</div> : null}
              {answer.sources.length > 0 && <div className={styles.citationSection}><div className={styles.citationTitle}>原文依据 <span>{answer.sources.length}</span></div>{answer.sources.map((source, index) => <button className={styles.citationCard} key={source.source_id} onClick={() => viewSource(source)}><span className={styles.citationIndex}>{String(index + 1).padStart(2, "0")}</span><span className={styles.citationBody}><span>{documents.find((doc) => doc.id === source.document_id)?.original_name ?? "已删除的资料"}</span><small>{source.locator?.page ? `第 ${source.locator.page} 页` : source.locator?.start != null ? `字符 ${source.locator.start}–${source.locator.end}` : "查看原文"}</small><em>{source.quote}</em></span><span className={styles.arrow}>↗</span></button>)}</div>}
              {answer.status !== "SUCCEEDED" && answer.status !== "PROCESSING" && <div className={styles.expired}>此问答状态：{statusLabel(answer.status)}。可在历史记录中查看。</div>}
            </article> : <div className={styles.emptyAnswer}><div className={styles.documentGlyph}>文</div><p>从一个具体问题开始</p><span>回答会附上可打开的原文来源，方便你核对关键事实。</span></div>}
            <form className={styles.askBox} onSubmit={ask}><textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={readyDocuments.length ? "例如：这个接口有哪些必填字段？" : "上传并等待至少一份资料就绪后即可提问。"} maxLength={4000} disabled={busy || readyDocuments.length === 0} rows={3} /><div className={styles.askActions}><span>问题会独立检索，不会引用上一轮对话作为上下文。</span>{busy ? <button className={styles.stopButton} type="button" onClick={() => void cancelQuestion()}>停止生成</button> : <button className={styles.primary} disabled={!readyDocuments.length || !draft.trim()}>提问 <span>↗</span></button>}</div></form>
          </div>

          <aside className={styles.documentPanel}><div className={styles.sectionHead}><div><span className={styles.eyebrow}>SOURCE LIBRARY</span><h2>资料 <span className={styles.documentCount}>{documents.length}</span></h2></div><label className={styles.iconUpload} aria-label="上传资料">＋<input type="file" accept=".txt,.md,.pdf" disabled={!selectedBase || working} onChange={(event) => { void upload(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label></div>
            {documents.length === 0 ? <div className={styles.emptyDocuments}><div>＋</div><strong>添加第一份资料</strong><span>支持 TXT、Markdown 和可读取文本的 PDF</span><small>最大 8 MiB · PDF 最多 200 页</small></div> : <div className={styles.documentList}>{documents.map((document) => <article key={document.id} className={styles.documentCard}><div className={styles.fileIcon}>{formatLabel(document.format)}</div><div className={styles.documentInfo}><strong title={document.original_name}>{document.original_name}</strong><span>{(document.byte_size / 1024).toFixed(0)} KB · {statusLabel(document.status)}</span>{document.status === "FAILED" && <small className={styles.failure}>索引失败，可尝试重建。</small>}</div><div className={styles.documentMenu}><button aria-expanded={openMenu === document.id} aria-label={`${document.original_name} 操作`} title="资料操作" onClick={() => setOpenMenu(openMenu === document.id ? "" : document.id)}>···</button>{openMenu === document.id && <div role="menu"><button role="menuitem" onClick={() => { setOpenMenu(""); window.document.getElementById(`update-${document.id}`)?.click(); }}>更新资料</button><button role="menuitem" onClick={() => { setOpenMenu(""); void rebuild(document); }}>重建索引</button><button role="menuitem" onClick={() => { setOpenMenu(""); void removeDocument(document); }}>删除资料</button></div>}<input id={`update-${document.id}`} type="file" accept=".txt,.md,.pdf" hidden onChange={(event) => { void upload(event.target.files?.[0], document); event.currentTarget.value = ""; }} /></div><div className={`${styles.statusDot} ${document.status === "READY" ? styles.statusReady : document.status === "FAILED" ? styles.statusFailed : ""}`} title={statusLabel(document.status)} /></article>)}</div>}
            <div className={styles.privacyNote}><span>◈</span><p><strong>资料访问范围</strong><br />仅你可以访问此知识库。上传文档会进入索引流程，只有状态显示“已就绪”后才参与问答。</p></div>
          </aside>
        </div>
      </section>

      {viewing && <div className={styles.modalBackdrop} role="presentation" onClick={closeViewer}><section className={styles.viewer} role="dialog" aria-modal="true" aria-label="原文依据" onClick={(event) => event.stopPropagation()}><header><div><span className={styles.eyebrow}>SOURCE EXCERPT</span><h2>{viewing.document.original_name}</h2></div><button aria-label="关闭原文" onClick={closeViewer}>×</button></header><blockquote>{viewing.source.quote}</blockquote>{viewing.text != null && <pre>{viewing.text}</pre>}{viewing.url && <iframe title={`${viewing.document.original_name} PDF 原文`} src={`${viewing.url}#page=${viewing.source.locator?.page ?? 1}`} />}</section></div>}
    </main>
  );
}
