"use client";

import { useEffect, useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";
import { useDocumentsContext, useKnowledgeContext, useStreamControls } from "@/components/workspace/workspace-provider";
import { useDraft } from "@/components/store";
import styles from "./chat.module.css";

function fitQuestion(input: HTMLTextAreaElement | null) {
  if (!input) return;
  input.style.height = "auto";
  const max = Number.parseFloat(getComputedStyle(input).maxHeight) || 144;
  input.style.height = `${Math.min(input.scrollHeight, max)}px`;
}

export function Composer({ onAsk }: { onAsk: (question: string) => void }) {
  const { draft, setDraft } = useDraft();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    fitQuestion(inputRef.current);
  }, [draft]);
  useEffect(() => {
    const resize = () => fitQuestion(inputRef.current);
    const input = inputRef.current;
    let width = input?.clientWidth;
    const observer = new ResizeObserver(() => {
      if (!input || input.clientWidth === width) return;
      width = input.clientWidth;
      fitQuestion(input);
    });
    if (input) observer.observe(input);
    window.addEventListener("resize", resize, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, []);
  const stream = useStreamControls();
  const knowledge = useKnowledgeContext();
  const { readyDocuments } = useDocumentsContext();
  const ready = readyDocuments.length > 0 && Boolean(knowledge.selectedBase);
  const placeholder = ready
    ? "例如：这个接口有哪些必填字段？"
    : "上传并等待至少一份资料就绪后即可提问。";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim() || !ready || stream.busy) return;
    onAsk(draft);
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  return (
    <form className={styles.composer} data-composite-field onSubmit={submit}>
      <textarea
        ref={inputRef}
        id="desk-question"
        name="question"
        aria-label="问题"
        aria-busy={stream.busy}
        autoComplete="off"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={keyDown}
        placeholder={placeholder}
        maxLength={4000}
        disabled={!ready || stream.busy}
        rows={1}
      />
      <div className={styles.composerFoot}>
        <span className={styles.composerHint}>
          {ready ? <><kbd>Enter</kbd> 发送 · <kbd>Shift</kbd> + <kbd>Enter</kbd> 换行</> : "至少需要一份已就绪的资料"}
        </span>
        {stream.busy ? (
          <button className={styles.stop} type="button" onClick={stream.cancel}>
            <Square size={13} aria-hidden="true" /> 停止生成
          </button>
        ) : (
          <button className={styles.send} type="submit" aria-label="提问" disabled={!ready || !draft.trim()}>
            提问 <ArrowUp size={15} aria-hidden="true" />
          </button>
        )}
      </div>
    </form>
  );
}
