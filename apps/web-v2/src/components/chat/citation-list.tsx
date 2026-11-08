"use client";

import type { Document, Source } from "@/services/api";
import styles from "./chat.module.css";

function locatorLabel(source: Source) {
  if (source.locator?.page != null) return `第 ${source.locator.page} 页`;
  if (source.locator?.start != null && source.locator?.end != null) {
    return `字符 ${source.locator.start}–${source.locator.end}`;
  }
  return "查看原文";
}

export function CitationList({
  sources,
  documents,
  onOpen,
}: {
  sources: Source[];
  documents: Document[];
  onOpen: (source: Source, documentName: string) => void;
}) {
  if (!sources.length) return null;
  return (
    <div className={styles.citations}>
      <div className={styles.citationTitle}>
        原文依据 <span>{sources.length}</span>
      </div>
      {sources.map((source, index) => {
        const name = documents.find((document) => document.id === source.document_id)?.original_name ?? "已删除的资料";
        return (
          <button
            key={source.source_id}
            className={styles.citation}
            onClick={() => onOpen(source, name)}
          >
            <span className={styles.citationIndex}>{String(index + 1).padStart(2, "0")}</span>
            <span className={styles.citationBody}>
              <span>{name}</span>
              <small>{locatorLabel(source)}</small>
              {source.quote && <em>{source.quote}</em>}
            </span>
            <span className={styles.citationArrow} aria-hidden="true">↗</span>
          </button>
        );
      })}
    </div>
  );
}
