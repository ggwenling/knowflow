"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowRight, Folder } from "lucide-react";
import Dashboard from "./dashboard";
import "@fontsource/dm-sans/latin-400.css";
import "@fontsource/dm-sans/latin-700.css";
import "@fontsource/dm-serif-display/latin-400.css";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ApiError, Document, KnowledgeBase, QuestionDetail, QuestionHistory, Source, streamQuestion, User } from "@/lib/api";
import styles from "./workspace.module.css";
import SourceViewer from "./source-viewer";

type Task = { task_id: string; status: string; failure_code: string | null };
type Page<T> = { items: T[]; has_more: boolean };
const contractVersion = "0.2.0";
const terminal = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const labels: Record<string, string> = {
  QUEUED: "等待处理", RUNNING: "正在建立索引", SUCCEEDED: "已就绪", READY: "已就绪",
  FAILED: "处理失败", CANCELLED: "已取消", PROCESSING: "正在处理",
};

function statusLabel(value: string) { return labels[value] ?? value; }
function formatLabel(value: string) { const format = value.toUpperCase(); return format === "PDF" || format === "MD" ? format : "TXT"; }
function messageOf(error: unknown) { return error instanceof Error ? error.message : "操作未能完成"; }
function ApiModeBanner({ externalOnly = false }: { externalOnly?: boolean }) {
  const [mode, setMode] = useState("unknown");
  useEffect(() => { fetch("/api/mode", { cache: "no-store" }).then((response) => response.json()).then((body) => setMode(body.mode)).catch(() => undefined); }, []);
  if (externalOnly && mode !== "external") return null;
  return mode === "synthetic" ? <div className={styles.modeBanner} role="status">合成模型 · 仅用于本地工程验证；不代表真实模型质量或费用</div>
    : mode === "external" ? <div className={styles.modeBanner} role="note">请只上传已获授权的资料。文档片段和问题会发送到当前配置的模型服务。</div>
      : <div className={styles.modeBanner} role="note">模型模式尚未配置。上传前请先确认资料获准使用，并确认模型服务的数据处理范围。</div>;
}

const Flow = dynamic(() => import("./flow"), { ssr: false });

export default function Workspace() {
  const [view, setView] = useState<"home" | "chat" | "bases" | "documents">("home");
  const [resetHelp, setResetHelp] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
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
  const [moreDocuments, setMoreDocuments] = useState(false);
  const [moreHistory, setMoreHistory] = useState(false);
  const [loadingPage, setLoadingPage] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [answer, setAnswer] = useState<QuestionDetail | null>(null);
  const [activeQuestion, setActiveQuestion] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const [viewing, setViewing] = useState<{ source: Source; documentName: string } | null>(null);
  const [openMenu, setOpenMenu] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const questionViewRef = useRef(0);
  const selectedBaseRef = useRef("");
  const baseGenerationRef = useRef(0);
  const refreshGenerationRef = useRef(0);
  const refreshInFlightRef = useRef<number | null>(null);
  const pageLoadingRef = useRef(false);
  const documentOffsetRef = useRef(0);
  const historyOffsetRef = useRef(0);
  const pollingTasksRef = useRef(new Set<string>());

  const selectBase = useCallback((baseId: string) => {
    if (selectedBaseRef.current !== baseId) {
      baseGenerationRef.current += 1;
      refreshInFlightRef.current = null; setRefreshing(false);
      setDocuments([]);
      setHistory([]);
      setMoreDocuments(false); setMoreHistory(false);
      setAnswer(null);
    }
    selectedBaseRef.current = baseId;
    setSelectedBase(baseId);
  }, []);

  function leaveQuestion() {
    questionViewRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
  }

  const applyRefresh = useCallback(async (baseId: string) => {
    const baseGeneration = baseGenerationRef.current;
    const requestGeneration = ++refreshGenerationRef.current;
    refreshInFlightRef.current = requestGeneration;
    setRefreshing(true);
    try {
    const [documentList, historyList] = await Promise.all([
      api<Page<Document>>(`knowledge-bases/${baseId}/documents?limit=50&offset=0`),
      api<Page<QuestionHistory>>("questions?limit=50&offset=0"),
    ]);
    if (selectedBaseRef.current !== baseId || baseGenerationRef.current !== baseGeneration || refreshGenerationRef.current !== requestGeneration) return null;
    setDocuments(documentList.items);
    setHistory(historyList.items);
    documentOffsetRef.current = documentList.items.length; historyOffsetRef.current = historyList.items.length;
    setMoreDocuments(Boolean(documentList.has_more)); setMoreHistory(Boolean(historyList.has_more));
    return documentList.items;
    } catch (error) {
      if (selectedBaseRef.current !== baseId || baseGenerationRef.current !== baseGeneration || refreshGenerationRef.current !== requestGeneration) return null;
      throw error;
    } finally {
      if (refreshInFlightRef.current === requestGeneration) {
        refreshInFlightRef.current = null;
        setRefreshing(false);
      }
    }
  }, []);

  async function loadMore(kind: "documents" | "history") {
    if (pageLoadingRef.current || refreshInFlightRef.current !== null || !selectedBaseRef.current) return;
    pageLoadingRef.current = true; setLoadingPage(true);
    const baseId = selectedBaseRef.current, generation = baseGenerationRef.current, refreshId = refreshGenerationRef.current;
    const isCurrent = () => selectedBaseRef.current === baseId && baseGenerationRef.current === generation && refreshGenerationRef.current === refreshId;
    try {
      if (kind === "documents") {
        const offset = documentOffsetRef.current;
        const result = await api<Page<Document>>(`knowledge-bases/${baseId}/documents?limit=50&offset=${offset}`);
        if (!isCurrent() || documentOffsetRef.current !== offset) return;
        documentOffsetRef.current += result.items.length;
        setDocuments((previous) => [...previous, ...result.items.filter((item) => !previous.some((old) => old.id === item.id))]);
        setMoreDocuments(Boolean(result.has_more));
        for (const document of result.items) {
          if (document.latest_task_id && document.latest_task_status && !terminal.has(document.latest_task_status)) {
            void pollDocument(document.id, document.latest_task_id, baseId).catch((error) => {
              if (isCurrent()) setNotice(messageOf(error));
            });
          }
        }
      } else {
        const offset = historyOffsetRef.current;
        const result = await api<Page<QuestionHistory>>(`questions?limit=50&offset=${offset}`);
        if (!isCurrent() || historyOffsetRef.current !== offset) return;
        historyOffsetRef.current += result.items.length;
        setHistory((previous) => [...previous, ...result.items.filter((item) => !previous.some((old) => old.question_id === item.question_id))]);
        setMoreHistory(Boolean(result.has_more));
      }
    } catch (error) { if (isCurrent()) setNotice(messageOf(error)); }
    finally { pageLoadingRef.current = false; setLoadingPage(false); }
  }

  const pollDocument = useCallback(async (documentId: string, taskId: string, baseId: string) => {
    const generation = baseGenerationRef.current;
    const pollKey = `${generation}:${taskId}`;
    const isCurrent = () => selectedBaseRef.current === baseId && baseGenerationRef.current === generation;
    if (pollingTasksRef.current.has(pollKey)) return;
    pollingTasksRef.current.add(pollKey);
    try {
      for (;;) {
        if (!isCurrent()) return;
        const [document, task] = await Promise.all([
          api<Document>(`documents/${documentId}`),
          api<Task>(`tasks/${taskId}`),
        ]);
        if (!isCurrent()) return;
        setDocuments((previous) => previous.map((item) => item.id === documentId ? document : item));
        if (terminal.has(task.status)) {
          await applyRefresh(baseId);
          if (isCurrent() && task.status !== "SUCCEEDED") {
            setNotice(task.failure_code ?? "索引未能完成；可以检查状态后重建。");
          }
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    } finally { pollingTasksRef.current.delete(pollKey); }
  }, [applyRefresh]);

  const refresh = useCallback(async (baseId: string) => {
    const documentList = await applyRefresh(baseId);
    if (!documentList) return;
    for (const document of documentList) {
      if (document.latest_task_id && document.latest_task_status && !terminal.has(document.latest_task_status)) {
        void pollDocument(document.id, document.latest_task_id, baseId).catch((error) => {
          if (selectedBaseRef.current === baseId) setNotice(messageOf(error));
        });
      }
    }
  }, [applyRefresh, pollDocument]);

  const loadBases = useCallback(async () => {
    const response = await api<{ items: KnowledgeBase[] }>("knowledge-bases?limit=50&offset=0");
    setBases(response.items);
    const chosen = response.items.find((item) => item.id === selectedBaseRef.current)?.id ?? response.items[0]?.id ?? "";
    selectBase(chosen);
    if (chosen) await refresh(chosen);
    else { setDocuments([]); setHistory([]); }
  }, [refresh, selectBase]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const current = await api<User>("me");
        if (!active) return;
        setUser(current);
        await loadBases().catch((error) => { if (active) setNotice(messageOf(error)); });
      } catch (error) {
        if (active && (error as ApiError).status !== 401) setAuthError(messageOf(error));
      } finally { if (active) setAuthLoading(false); }
    })();
    return () => { active = false; };
  }, [loadBases]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const readyDocuments = useMemo(() => documents.filter((document) => document.status === "READY" && document.active_index_version_id), [documents]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setAuthError(""); setNotice(""); setBusy(true);
    try {
      await api(`auth/${authMode}`, { method: "POST", body: JSON.stringify({ contract_version: contractVersion, email, password }) });
      setUser(await api<User>("me"));
      setPassword("");
      setShowPassword(false);
      await loadBases().catch((error) => setNotice(messageOf(error)));
    } catch (error) { setAuthError(messageOf(error)); }
    finally { setBusy(false); }
  }

  async function signOut() {
    try { await api("auth/logout", { method: "POST", body: "{}" }); } catch { /* The proxy clears expired sessions too. */ }
    leaveQuestion(); setView("home"); setAuthMode("login"); setResetHelp(false); setShowPassword(false);
    setDraft(""); setNotice(""); setViewing(null); setOpenMenu(""); selectBase(""); setUser(null); setBases([]); setDocuments([]); setHistory([]); setAnswer(null);
  }

  async function createBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const element = event.currentTarget; const form = new FormData(element); const name = String(form.get("name") ?? "").trim();
    if (!name) return;
    setWorking(true); setNotice("");
    try {
      await api("knowledge-bases", { method: "POST", body: JSON.stringify({ contract_version: contractVersion, name }) });
      element.reset();
      await loadBases();
    } catch (error) { setNotice(messageOf(error)); }
    finally { setWorking(false); }
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
    const questionView = questionViewRef.current;
    setWorking(true); setNotice("");
    try {
      await api(`documents/${document.id}`, { method: "DELETE" });
      if (selectedBaseRef.current !== selectedBase) return;
      setDocuments((previous) => previous.filter((item) => item.id !== document.id));
      setAnswer((current) => current?.sources.some((source) => source.document_id === document.id) ? null : current);
      if (questionViewRef.current === questionView && answer?.sources.some((source) => source.document_id === document.id)) {
        setNotice("该文档已删除，相关来源已失效。");
      }
      await refresh(selectedBase);
    } catch (error) {
      if (selectedBaseRef.current === selectedBase && questionViewRef.current === questionView) setNotice(messageOf(error));
    }
    finally { setWorking(false); }
  }

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBase || !readyDocuments.length || !draft.trim() || busy) return;
    setView("chat");
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
        (sources, hasAnswer) => setAnswer((old) => isCurrent() && old ? { ...old, sources, has_answer: hasAnswer } : old));
      if (!isCurrent()) return;
      setAnswer((old) => isCurrent() && old ? { ...old, status: "SUCCEEDED", finished_at: new Date().toISOString() } : old);
      await refresh(selectedBase).catch((error) => setNotice(messageOf(error)));
    } catch (error) {
      if (!isCurrent()) return;
      const reason = controller.signal.aborted ? "用户停止生成" : messageOf(error);
      const cancelled = controller.signal.aborted || error instanceof DOMException && error.name === "AbortError";
      setAnswer((old) => isCurrent() && old ? { ...old, status: cancelled ? "CANCELLED" : "FAILED", failure_code: reason, has_answer: null, sources: [] } : old);
      if (!controller.signal.aborted) setNotice(messageOf(error));
      await refresh(selectedBase).catch(() => undefined);
    } finally { if (isCurrent()) { abortRef.current = null; setBusy(false); } }
  }

  async function cancelQuestion() { abortRef.current?.abort(); setNotice("正在停止请求。若生成已经开始，请在历史记录里确认状态，不会自动重发。"); }

  async function openHistory(item: QuestionHistory) {
    leaveQuestion();
    setView("chat");
    const questionView = questionViewRef.current;
    selectBase(item.knowledge_base_id);
    const isCurrent = () => selectedBaseRef.current === item.knowledge_base_id && questionViewRef.current === questionView;
    try {
      await refresh(item.knowledge_base_id);
      if (!isCurrent()) return;
      const detail = await api<QuestionDetail>(`questions/${item.question_id}`);
      if (isCurrent()) setAnswer(detail);
    }
    catch (error) { if (isCurrent()) setNotice(messageOf(error)); }
  }

  async function deleteHistory(item: QuestionDetail) {
    if (!item.question_id || !window.confirm("删除这条问答记录？此操作无法撤销。")) return;
    try {
      await api(`questions/${item.question_id}`, { method: "DELETE" });
      setAnswer(null);
      if (selectedBase) await refresh(selectedBase);
    } catch (error) { setNotice(messageOf(error)); }
  }

  function viewSource(source: Source) {
    const document = documents.find((item) => item.id === source.document_id);
    if (!document) { setNotice("找不到来源对应的文档。"); return; }
    setViewing({ source, documentName: document.original_name });
  }

  function closeViewer() { setViewing(null); }

  if (authLoading) return <main className={styles.loading}>正在检查登录状态…</main>;
  if (!user) return (
    <main className={styles.loginPage} lang="en">
      <div className="loginFlow" aria-hidden="true"><Flow /></div>
      <section className={styles.loginContent}>
        <div className={styles.loginBrand}>KnowFlow</div>
        <h1>{authMode === "login" ? <>Knowledge<br />that flows.</> : <>Create your<br />account.</>}</h1>
        <p>{authMode === "login" ? <>Sign in to KnowFlow and keep your<br className={styles.loginBreak} /> knowledge in motion.</> : "Create an account to start building your knowledge base."}</p>
        <form className={styles.loginForm} onSubmit={submitAuth}>
          <label htmlFor="auth-email">Email</label>
          <input id="auth-email" type="email" placeholder="Enter your email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="auth-password">Password</label>
          <div className={styles.passwordField}>
            <input id="auth-password" type={showPassword ? "text" : "password"} placeholder="Enter your password" autoComplete={authMode === "login" ? "current-password" : "new-password"} minLength={12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
            <button type="button" aria-controls="auth-password" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword(!showPassword)}>{showPassword ? "Hide" : "Show"}</button>
          </div>
          {authMode === "register" && <small>Use 12–128 characters.</small>}
          {authError && <p className={styles.error} lang="zh-CN" role="alert">{authError}</p>}
          <button className={styles.loginSubmit} disabled={busy}>{busy ? "Please wait…" : authMode === "login" ? "Sign in" : "Create account"}</button>
        </form>
        <div className={styles.loginLinks}>
          {authMode === "login" && <button type="button" onClick={() => setResetHelp(!resetHelp)} aria-expanded={resetHelp}>Forgot password?</button>}
          <button type="button" disabled={busy} onClick={() => {
            setAuthMode(authMode === "login" ? "register" : "login");
            setAuthError(""); setPassword(""); setShowPassword(false); setResetHelp(false);
          }}>{authMode === "login" ? "Create an account" : "Back to sign in"}</button>
        </div>
        {resetHelp && <p className={styles.resetHelp} role="status">Self-service password reset is currently unavailable.</p>}
      </section>
    </main>
  );

  function chooseBase(baseId: string) {
    if (baseId === selectedBaseRef.current) return;
    leaveQuestion();
    selectBase(baseId);
    void refresh(baseId).catch((error) => {
      if (selectedBaseRef.current === baseId) setNotice(messageOf(error));
    });
  }

  if (view === "home") return (
    <Dashboard
      email={user.email} bases={bases} selectedBase={selectedBase} history={history}
      documentCount={refreshing ? undefined : documents.length} moreDocuments={moreDocuments}
      draft={draft} canAsk={readyDocuments.length > 0 && !busy} busy={busy}
      notice={notice} onDismissNotice={() => setNotice("")}
      modelNotice={<ApiModeBanner externalOnly />}
      onDraftChange={setDraft} onAsk={ask} onChooseBase={chooseBase}
      onOpenBase={(id) => { chooseBase(id); setView("documents"); }}
      onOpenHistory={openHistory} onNavigate={setView} onSignOut={signOut} onCreateBase={() => {
        setView("bases");
        requestAnimationFrame(() => document.getElementById("new-base-name")?.focus());
      }}
    />
  );

  const selectedKnowledgeBase = bases.find((base) => base.id === selectedBase);
  return (
    <main className={styles.appShell}>
      <aside className={styles.sidebar}>
        <Link className={styles.brand} href="/" onClick={(event) => { event.preventDefault(); setView("home"); }}><span className={styles.brandMark}>K</span><span>KnowFlow<small>文档核验工作台</small></span></Link>
        <nav className={styles.deskNav} aria-label="工作台">
          <button onClick={() => setView("home")}>首页</button>
          <button aria-current={view === "chat" ? "page" : undefined} onClick={() => setView("chat")}>对话</button>
          <button aria-current={view === "bases" ? "page" : undefined} onClick={() => setView("bases")}>知识库</button>
          <button aria-current={view === "documents" ? "page" : undefined} onClick={() => setView("documents")}>文档</button>
        </nav>
        <div className={styles.sideLabel}>我的知识库</div>
        <div className={styles.baseList}>{bases.map((base) => <button key={base.id} className={`${styles.baseItem} ${selectedBase === base.id ? styles.activeBase : ""}`} onClick={() => { leaveQuestion(); selectBase(base.id); setAnswer(null); void refresh(base.id).catch((error) => { if (selectedBaseRef.current === base.id) setNotice(messageOf(error)); }); }}><span className={styles.baseGlyph}>▤</span>{base.name}</button>)}</div>
        {bases.length === 0 && <p className={styles.sideEmpty}>这里还没有知识库。</p>}
        <form className={styles.newBase} onSubmit={createBase}><input id="new-base-name" aria-label="新知识库名称" name="name" placeholder="新建知识库名称" maxLength={200} /><button aria-label="创建知识库" disabled={working}>＋</button></form>
        <div className={styles.sideLabel}>最近问答</div>
        <div className={styles.historyList}>{history.map((item) => <button key={item.question_id} className={styles.historyItem} onClick={() => openHistory(item)}><span>{item.question}</span><small>{statusLabel(item.status)}</small></button>)}{moreHistory && <button className={styles.textButton} disabled={loadingPage || refreshing} onClick={() => void loadMore("history")}>加载更多问答</button>}</div>
        <div className={styles.account}><span className={styles.avatar}>{user.email.slice(0, 1).toUpperCase()}</span><span className={styles.accountText}>{user.email}<small>个人空间</small></span><button className={styles.textButton} onClick={signOut}>退出</button></div>
      </aside>

      <section className={styles.mainColumn}>
        <header className={styles.topbar}><div><span className={styles.eyebrow}>KNOWLEDGE DESK</span><h1>{selectedKnowledgeBase?.name ?? "开始整理你的资料"}</h1></div><div className={styles.topActions}><span className={styles.readyCount}>{readyDocuments.length} 份资料可用于问答</span><label className={styles.uploadButton}>＋ 上传资料<input type="file" accept=".txt,.md,.pdf" disabled={!selectedBase || working} onChange={(event) => { void upload(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label></div></header>
        <ApiModeBanner />
        {notice && <div className={styles.notice} role="status"><span>{notice}</span><button aria-label="关闭提示" onClick={() => setNotice("")}>×</button></div>}
        {view === "bases" ? <section className={styles.library} aria-label="全部知识库">
          <h2>全部知识库</h2>
          <div className={styles.libraryGrid}>{bases.map((base) => (
            <button key={base.id} onClick={() => { chooseBase(base.id); setView("documents"); }}>
              <Folder size={20} /><span>{base.name}</span><ArrowRight size={18} />
            </button>
          ))}</div>
          {!bases.length && <p>创建第一座知识库，开始整理你的资料。</p>}
        </section> : <div className={view === "chat" ? styles.workArea : styles.documentsView}>
          {view === "chat" && <div className={styles.chatColumn}>
            <div className={styles.sectionHead}><div><span className={styles.eyebrow}>ASK YOUR DOCUMENTS</span><h2>问答与依据</h2></div><span className={styles.singleTurn}>单轮问答</span></div>
            {answer ? <article className={styles.answerCard}>
              <div className={styles.questionLine}><span className={styles.questionMark}>问</span><p>{answer.question || activeQuestion}</p>{answer.question_id && answer.status !== "PROCESSING" && <button className={styles.deleteQuestion} onClick={() => void deleteHistory(answer)}>删除记录</button>}</div>
              {answer.answer ? <div className={styles.answerText}>{answer.answer}</div> : answer.status === "PROCESSING" ? <div className={styles.generating}><span className={styles.pulse} />正在检索并生成回答…</div> : null}
              {answer.sources.length > 0 && <div className={styles.citationSection}><div className={styles.citationTitle}>原文依据 <span>{answer.sources.length}</span></div>{answer.sources.map((source, index) => <button className={styles.citationCard} key={source.source_id} onClick={() => viewSource(source)}><span className={styles.citationIndex}>{String(index + 1).padStart(2, "0")}</span><span className={styles.citationBody}><span>{documents.find((doc) => doc.id === source.document_id)?.original_name ?? "已删除的资料"}</span><small>{source.locator?.page ? `第 ${source.locator.page} 页` : source.locator?.start != null ? `字符 ${source.locator.start}–${source.locator.end}` : "查看原文"}</small><em>{source.quote}</em></span><span className={styles.arrow}>↗</span></button>)}</div>}
              {answer.status !== "SUCCEEDED" && answer.status !== "PROCESSING" && <div className={styles.expired}>此问答状态：{statusLabel(answer.status)}。可在历史记录中查看。</div>}
            </article> : <div className={styles.emptyAnswer}><div className={styles.documentGlyph}>文</div><p>从一个具体问题开始</p><span>回答会附上可打开的原文来源，方便你核对关键事实。</span></div>}
            <form className={styles.askBox} onSubmit={ask}><textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={readyDocuments.length ? "例如：这个接口有哪些必填字段？" : "上传并等待至少一份资料就绪后即可提问。"} maxLength={4000} disabled={busy || readyDocuments.length === 0} rows={3} /><div className={styles.askActions}><span>问题会独立检索，不会引用上一轮对话作为上下文。</span>{busy ? <button className={styles.stopButton} type="button" onClick={() => void cancelQuestion()}>停止生成</button> : <button className={styles.primary} disabled={!readyDocuments.length || !draft.trim()}>提问 <span>↗</span></button>}</div></form>
          </div>}

          <aside className={styles.documentPanel}><div className={styles.sectionHead}><div><span className={styles.eyebrow}>SOURCE LIBRARY</span><h2>资料 <span className={styles.documentCount}>{documents.length}</span></h2></div><label className={styles.iconUpload} aria-label="上传资料">＋<input type="file" accept=".txt,.md,.pdf" disabled={!selectedBase || working} onChange={(event) => { void upload(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label></div>
            {documents.length === 0 ? <div className={styles.emptyDocuments}><div>＋</div><strong>添加第一份资料</strong><span>支持 TXT、Markdown 和可读取文本的 PDF</span><small>最大 8 MiB · PDF 最多 200 页</small></div> : <div className={styles.documentList}>{documents.map((document) => <article key={document.id} className={styles.documentCard}><div className={styles.fileIcon}>{formatLabel(document.format)}</div><div className={styles.documentInfo}><strong title={document.original_name}>{document.original_name}</strong><span>{(document.byte_size / 1024).toFixed(0)} KB · {statusLabel(document.status)}</span>{document.status === "FAILED" && <small className={styles.failure}>索引失败，可尝试重建。</small>}</div><div className={styles.documentMenu}><button aria-expanded={openMenu === document.id} aria-label={`${document.original_name} 操作`} title="资料操作" onClick={() => setOpenMenu(openMenu === document.id ? "" : document.id)}>···</button>{openMenu === document.id && <div role="menu"><button role="menuitem" onClick={() => { setOpenMenu(""); window.document.getElementById(`update-${document.id}`)?.click(); }}>更新资料</button><button role="menuitem" onClick={() => { setOpenMenu(""); void rebuild(document); }}>重建索引</button><button role="menuitem" onClick={() => { setOpenMenu(""); void removeDocument(document); }}>删除资料</button></div>}<input id={`update-${document.id}`} type="file" accept=".txt,.md,.pdf" hidden onChange={(event) => { void upload(event.target.files?.[0], document); event.currentTarget.value = ""; }} /></div><div className={`${styles.statusDot} ${document.status === "READY" ? styles.statusReady : document.status === "FAILED" ? styles.statusFailed : ""}`} title={statusLabel(document.status)} /></article>)}</div>}
            {moreDocuments && <button className={styles.textButton} disabled={loadingPage || refreshing} onClick={() => void loadMore("documents")}>加载更多资料</button>}
            <div className={styles.privacyNote}><span>◈</span><p><strong>资料访问范围</strong><br />仅你可以访问此知识库。上传文档会进入索引流程，只有状态显示“已就绪”后才参与问答。</p></div>
          </aside>
        </div>}
      </section>

      {viewing && <SourceViewer source={viewing.source} documentName={viewing.documentName} onClose={closeViewer} />}
    </main>
  );
}
