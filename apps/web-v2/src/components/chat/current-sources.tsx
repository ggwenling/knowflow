"use client";

import { memo } from "react";
import { useStreamContext, useDocumentsContext } from "@/components/workspace/workspace-provider";
import type { Document, Source } from "@/services/api";
import styles from "./chat.module.css";

type OpenSource = (source: Source, documentName: string, trigger: HTMLButtonElement) => void;

const SourceLinks = memo(function SourceLinks({ sources, documents, onOpen }: { sources: Source[]; documents: Document[]; onOpen: OpenSource }) {
  if (!sources.length) return null;
  return (
    <section className={styles.currentSources} aria-label="本次引用">
      <h3>本次引用 <span>{sources.length}</span></h3>
      {sources.map((source, index) => {
        const name = documents.find((document) => document.id === source.document_id)?.original_name ?? "已删除的资料";
        return (
          <button key={source.source_id} onClick={(event) => onOpen(source, name, event.currentTarget)}>
            <span className={styles.sourceNumber}>{String(index + 1).padStart(2, "0")}</span>
            <span className={styles.sourceName}>{name}</span>
            <span aria-hidden="true">↗</span>
          </button>
        );
      })}
    </section>
  );
});

/** Only this small subscription sees deltas; stable source arrays bail out the list. */
export function CurrentSources({ onOpen }: { onOpen: OpenSource }) {
  const { answer } = useStreamContext();
  const { documents } = useDocumentsContext();
  if (!answer) return null;
  return <SourceLinks sources={answer.sources} documents={documents} onOpen={onOpen} />;
}
