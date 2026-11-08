"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Bell, Sparkles } from "lucide-react";
import { useWorkspaceDataContext } from "@/components/workspace/workspace-provider";
import { Button } from "@/components/ui/button";
import { ShortcutGrid } from "./shortcut-grid";
import { RecentPanels } from "./recent-panels";
import styles from "./home-view.module.css";

const Wave = dynamic(() => import("@/components/home-wave"), { ssr: false });

function ModelNotice() {
  const [mode, setMode] = useState("unknown");
  useEffect(() => {
    fetch("/api/mode", { cache: "no-store" })
      .then((response) => response.json())
      .then((body: { mode?: string }) => setMode(body.mode ?? "unknown"))
      .catch(() => undefined);
  }, []);

  if (mode === "synthetic") {
    return <div className={styles.modeNote} role="status">合成模型 · 仅用于本地工程验证，不代表真实模型质量或费用</div>;
  }
  if (mode === "external") {
    return <div className={styles.modeNote} role="note">文档片段与问题会发送到当前配置的模型服务，请只上传已获授权的资料。</div>;
  }
  return <div className={styles.modeNote} role="note">模型模式尚未配置，上传前请确认资料用途与模型服务的数据处理范围。</div>;
}

export function HomeView() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const { session, knowledge, documents, questions, stream, readyDocuments, draft, setDraft, clearDraft } = useWorkspaceDataContext();
  const inputRef = useRef<HTMLInputElement>(null);
  const [notice, setNotice] = useState("");

  const docCount = knowledge.selectedBase && !documents.refreshing && !documents.hasMore
    ? documents.documents.length
    : undefined;

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || !knowledge.selectedBase || !readyDocuments.length || stream.busy) return;
    clearDraft();
    router.push("/conversations");
    void stream.ask(question, knowledge.selectedBase);
  }

  const uploadHref = knowledge.selectedBase
    ? `/knowledge-bases/${knowledge.selectedBase}`
    : "/knowledge-bases?create=1";

  async function retry() {
    setNotice("");
    await knowledge.load();
    await documents.refresh(knowledge.selectedBase);
  }

  return (
    <motion.div
      className={styles.home}
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.32 }}
    >
      <div className={styles.wave} aria-hidden="true">
        <div className={`home-art ${styles.art}`}>
          <Wave />
        </div>
      </div>

      <header className={styles.header}>
        <details className={styles.notifications}>
          <summary aria-label="通知"><Bell size={21} strokeWidth={1.6} /></summary>
          <div className={styles.popover}>
            <strong>通知</strong>
            <p>暂无新通知。</p>
          </div>
        </details>
      </header>

      <section className={styles.hero} aria-labelledby="home-title">
        <p className={styles.eyebrow}>Retrieval-augmented workspace</p>
        <h1 id="home-title">KnowFlow</h1>
        <p className={styles.lead}>基于 RAG 的智能知识管理与问答系统</p>
        <form className={styles.ask} onSubmit={ask}>
          <Sparkles size={22} strokeWidth={1.5} aria-hidden="true" />
          <input
            ref={inputRef}
            name="question"
            aria-label="向知识库提问"
            autoComplete="off"
            value={draft}
            maxLength={4000}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="向你的知识库提问…"
          />
          <button
            aria-label="提问"
            disabled={!draft.trim() || !readyDocuments.length || stream.busy}
            title={stream.busy ? "正在生成回答" : !readyDocuments.length ? "请先上传文档，等待索引就绪后提问" : "发送问题"}
          >
            <ArrowRight size={21} strokeWidth={1.8} />
          </button>
        </form>
        {knowledge.bases.length > 1 && (
          <label className={styles.scope}>
            提问知识库
            <select
              aria-label="选择知识库"
              value={knowledge.selectedBase}
              onChange={(event) => knowledge.selectBase(event.target.value)}
            >
              {knowledge.bases.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
        )}
      </section>

      <ModelNotice />
      {(notice || stream.notice) && (
        <div className={styles.notice} role="status">
          <span>{notice || stream.notice}</span>
          <Button variant="text" size="sm" onClick={() => { setNotice(""); stream.clearNotice(); void retry(); }}>重试</Button>
          <button aria-label="关闭提示" onClick={() => { setNotice(""); stream.clearNotice(); }}>×</button>
        </div>
      )}

      <ShortcutGrid uploadHref={uploadHref} />

      <RecentPanels
        bases={knowledge.bases}
        selectedBase={knowledge.selectedBase}
        documentCount={docCount}
        moreDocuments={documents.hasMore}
        history={questions.history}
        loading={knowledge.loading}
        onCreateBase={() => router.push("/knowledge-bases?create=1")}
        onFocusComposer={() => inputRef.current?.focus()}
      />

      <footer className={styles.footer}>
        <span>{session.user?.email}</span>
        <span>{knowledge.bases.length} 个知识库 · {questions.history.length} 条问答</span>
      </footer>
    </motion.div>
  );
}
