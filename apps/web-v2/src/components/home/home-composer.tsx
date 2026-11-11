"use client";

import { useRouter } from "next/navigation";
import { memo, type FormEvent, type RefObject } from "react";
import { ArrowRight, Layers, Sparkles } from "lucide-react";
import { useDraft } from "@/components/store";
import { useDocumentsContext, useKnowledgeContext, useStreamControls } from "@/components/workspace/workspace-provider";
import styles from "./home-view.module.css";

const HomeScope = memo(function HomeScope() {
  const knowledge = useKnowledgeContext();
  return knowledge.bases.length > 1 ? (
    <label className={styles.scope}>
      <Layers size={16} strokeWidth={1.5} aria-hidden="true" />
      <span>提问知识库</span>
      <select aria-label="选择知识库" value={knowledge.selectedBase} onChange={(event) => knowledge.selectBase(event.target.value)}>
        {knowledge.bases.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
      </select>
    </label>
  ) : <span className={styles.scopeStatic}><Layers size={16} aria-hidden="true" /> {knowledge.bases.find((base) => base.id === knowledge.selectedBase)?.name ?? "先创建知识库"}</span>;
});

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
    <form className={styles.ask} data-composite-field onSubmit={ask}>
      <div className={styles.askMain}>
        <Sparkles size={20} strokeWidth={1.5} aria-hidden="true" />
        <input ref={inputRef} name="question" aria-label="向知识库提问" autoComplete="off" value={draft} maxLength={4000} onChange={(event) => setDraft(event.target.value)} placeholder="向你的知识库提问…" />
        <button aria-label="提问" disabled={!draft.trim() || !readyDocuments.length || stream.busy} title={stream.busy ? "正在生成回答" : !readyDocuments.length ? "请先上传文档，等待索引就绪后提问" : "发送问题"}>
          <ArrowRight size={20} strokeWidth={1.5} aria-hidden="true" />
        </button>
      </div>
      <div className={styles.askFoot}>
        <HomeScope />
        <span className={styles.askHelper}>每次提问独立检索</span>
      </div>
    </form>
  );
}
