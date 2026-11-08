"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { toast } from "sonner";
import { Clipboard, Sparkles, SquarePen } from "lucide-react";
import { useWorkspaceDataContext } from "@/components/workspace/workspace-provider";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { StatusBadge } from "@/components/ui/status-badge";
import { questionStatusLabel } from "@/lib/format";
import { CitationList } from "./citation-list";
import styles from "./chat.module.css";

const Markdown = dynamic(() => import("./markdown-answer"), {
  ssr: false,
  loading: () => <span className={styles.answerLoading}>正在排版…</span>,
});

export function AnswerPanel({
  onOpenSource,
  onEditQuestion,
  onDeleted,
}: {
  onOpenSource: (source: import("@/services/api").Source, documentName: string) => void;
  onEditQuestion: (question: string) => void;
  onDeleted: (questionId: string) => void;
}) {
  const { stream, documents, knowledge } = useWorkspaceDataContext();
  const answer = stream.answer;
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (!answer) {
    return (
      <div className={styles.answerEmpty}>
        <span className={styles.emptyMark} aria-hidden="true">问</span>
        <h2>从一个具体问题开始</h2>
        <p>回答会附上可打开的原文来源，方便你核对关键事实。每次提问独立检索，不会把上一轮回答当作上下文。</p>
        <div className={styles.examples}>
          {["这份资料的核心结论是什么？", "有哪些必须满足的前提条件？", "请给出原文中对应的依据。"].map((example) => (
            <button key={example} onClick={() => onEditQuestion(example)}>
              <Sparkles size={13} aria-hidden="true" />
              {example}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const processing = answer.status === "PROCESSING";
  const finished = !processing && answer.status !== "SUCCEEDED";
  const hasText = Boolean(answer.answer);

  async function copy() {
    if (!answer?.answer) return;
    try {
      await navigator.clipboard.writeText(answer.answer);
      toast.success("回答已复制");
    } catch {
      toast.error("复制失败，请手动选择文本。");
    }
  }

  async function remove() {
    if (!answer?.question_id) return;
    const questionId = answer.question_id;
    const removed = await stream.remove(questionId);
    setConfirmDelete(false);
    if (removed) {
      toast.success("问答记录已删除");
      onEditQuestion("");
      onDeleted(questionId);
    }
  }

  return (
    <article className={styles.answerCard}>
      <header className={styles.questionLine}>
        <span className={styles.questionMark} aria-hidden="true">问</span>
        <p>{answer.question}</p>
        <div className={styles.questionActions}>
          <StatusBadge status={answer.status} kind="question" />
          {answer.answer && (
            <button className={styles.iconAction} onClick={() => void copy()} aria-label="复制回答" title="复制回答">
              <Clipboard size={14} />
            </button>
          )}
          {answer.question_id && !processing && (
            <button
              className={styles.iconAction}
              onClick={() => setConfirmDelete(true)}
              aria-label="删除这条问答"
              title="删除这条问答"
            >
              ×
            </button>
          )}
        </div>
      </header>

      <div className={styles.answerBody} aria-live="polite">
        {processing && (
          <div className={styles.generating}>
            <span className={styles.pulse} aria-hidden="true" />
            正在检索并生成回答…
          </div>
        )}
        {hasText && (
          processing ? (
            <p className={styles.streamingText}>{answer.answer}<span className={styles.caret} aria-hidden="true" /></p>
          ) : (
            <Markdown text={answer.answer ?? ""} />
          )
        )}
        {!processing && !hasText && answer.has_answer === false && (
          <p className={styles.refusal}>没有足够的资料证据回答这个问题。</p>
        )}
      </div>

      <CitationList sources={answer.sources} documents={documents.documents} onOpen={onOpenSource} />

      {finished && (
        <div className={styles.answerEnd}>
          <p>此问答状态：{questionStatusLabel(answer.status)}。可在历史记录中查看。</p>
          <div className={styles.answerEndActions}>
            <button onClick={() => onEditQuestion(answer.question)}>
              <SquarePen size={13} aria-hidden="true" /> 重新编辑问题
            </button>
            {knowledge.selectedBase && (
              <button onClick={() => void stream.ask(answer.question, knowledge.selectedBase)}>重试提问</button>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="删除这条问答记录？"
        description="记录与来源快照会被移除，此操作无法撤销。原始资料不受影响。"
        onConfirm={() => void remove()}
      />
    </article>
  );
}
