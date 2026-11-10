"use client";

import { useRouter } from "next/navigation";
import type { FormEvent, RefObject } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import { useDraft } from "@/components/store";
import { useDocumentsContext, useKnowledgeContext, useStreamControls } from "@/components/workspace/workspace-provider";
import styles from "./home-view.module.css";

export function HomeComposer({ inputRef }: { inputRef: RefObject<HTMLInputElement | null> }) {
  const router = useRouter();
  const { draft, setDraft, clearDraft } = useDraft();
  const knowledge = useKnowledgeContext();
  const { readyDocuments } = useDocumentsContext();
  const stream = useStreamControls();
  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || !knowledge.selectedBase || !readyDocuments.length || stream.busy) return;
    clearDraft();
    router.push("/conversations");
    void stream.ask(question, knowledge.selectedBase);
  }
  return (
    <form className={styles.ask} onSubmit={ask}>
      <Sparkles size={22} strokeWidth={1.5} aria-hidden="true" />
      <input ref={inputRef} name="question" aria-label="向知识库提问" autoComplete="off" value={draft} maxLength={4000} onChange={(event) => setDraft(event.target.value)} placeholder="向你的知识库提问…" />
      <kbd className={styles.askKbd} aria-hidden="true">↵</kbd>
      <button aria-label="提问" disabled={!draft.trim() || !readyDocuments.length || stream.busy} title={stream.busy ? "正在生成回答" : !readyDocuments.length ? "请先上传文档，等待索引就绪后提问" : "发送问题"}>
        <ArrowRight size={21} strokeWidth={1.8} aria-hidden="true" />
      </button>
    </form>
  );
}
