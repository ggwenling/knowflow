"use client";

import { useRef, useState } from "react";
import { DocumentActions } from "./document-actions";
import { acceptedFileTypes } from "@/lib/upload-rules";
import { FileText } from "lucide-react";
import type { Document } from "@/services/api";
import { formatBytes, formatLabel } from "@/lib/format";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { StatusBadge } from "@/components/ui/status-badge";
import styles from "./knowledge.module.css";

export function DocumentList({
  documents,
  busy,
  onUpdate,
  onRebuild,
  onDelete,
}: {
  documents: Document[];
  busy: boolean;
  onUpdate: (file: File | undefined, document: Document) => void;
  onRebuild: (document: Document) => void;
  onDelete: (document: Document) => Promise<void>;
}) {
  const [pending, setPending] = useState<Document | null>(null);
  const [working, setWorking] = useState(false);
  const target = useRef<Document | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  function pickUpdate(document: Document) {
    target.current = document;
    fileInput.current?.click();
  }

  async function confirmDelete() {
    if (!pending) return;
    if (working || busy) return;
    setWorking(true);
    try { await onDelete(pending); setPending(null); } finally { setWorking(false); }
  }

  return (
    <>
      <div className={styles.docList}>
        {documents.map((document) => (
          <article className={styles.docCard} key={document.id}>
            <span className={styles.docFormat}>{formatLabel(document.format)}</span>
            <span className={styles.docName}>
              <strong title={document.original_name}>{document.original_name}</strong>
              <small>{formatBytes(document.byte_size)} · {formatLabel(document.format)}</small>
            </span>
            <span className={styles.docStatus}>
              <StatusBadge status={document.status} />
              {document.status === "FAILED" && <small>可尝试重建索引</small>}
            </span>
            <DocumentActions document={document} busy={busy} onUpdate={pickUpdate} onRebuild={onRebuild} onDelete={setPending} />
          </article>
        ))}
        {!documents.length && (
          <div className={styles.docEmptyRow}>
            <FileText size={18} strokeWidth={1.5} aria-hidden="true" />
            <span>没有符合条件的资料。</span>
          </div>
        )}
      </div>

      <input
        ref={fileInput}
        type="file"
        accept={acceptedFileTypes}
        aria-label="选择更新资料"
        hidden
        onChange={(event) => {
          if (target.current && event.target.files?.[0]) onUpdate(event.target.files[0], target.current);
          event.currentTarget.value = "";
        }}
      />

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => { if (!open) setPending(null); }}
        title={`删除「${pending?.original_name ?? ""}」？`}
        description="删除后，该文档不再参与问答，已有问答中的相关来源会失效。此操作无法撤销。"
        confirmLabel={working ? "正在删除…" : "确认删除"}
        onConfirm={() => void confirmDelete()}
        busy={working || busy}
      />
    </>
  );
}
