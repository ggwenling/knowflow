"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, MoreHorizontal } from "lucide-react";
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
  const [openMenu, setOpenMenu] = useState("");
  const [pending, setPending] = useState<Document | null>(null);
  const [working, setWorking] = useState(false);
  const target = useRef<Document | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!openMenu) return;
    const close = (event: MouseEvent) => {
      const element = event.target as HTMLElement;
      if (!element.closest("[data-doc-menu]")) setOpenMenu("");
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [openMenu]);

  function pickUpdate(document: Document) {
    setOpenMenu("");
    target.current = document;
    fileInput.current?.click();
  }

  async function confirmDelete() {
    if (!pending) return;
    setWorking(true);
    await onDelete(pending);
    setWorking(false);
    setPending(null);
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
            <div className={styles.docMenu} data-doc-menu>
              <button
                aria-label={`${document.original_name} 操作`}
                aria-expanded={openMenu === document.id}
                onClick={() => setOpenMenu(openMenu === document.id ? "" : document.id)}
              >
                <MoreHorizontal size={17} />
              </button>
              {openMenu === document.id && (
                <div role="menu" className={styles.docMenuPanel}>
                  <button role="menuitem" onClick={() => pickUpdate(document)}>更新资料</button>
                  <button role="menuitem" onClick={() => { setOpenMenu(""); onRebuild(document); }}>重建索引</button>
                  <button role="menuitem" className={styles.dangerItem} onClick={() => { setOpenMenu(""); setPending(document); }}>
                    删除资料
                  </button>
                </div>
              )}
            </div>
          </article>
        ))}
        {!documents.length && (
          <div className={styles.docEmptyRow}>
            <FileText size={18} strokeWidth={1.4} aria-hidden="true" />
            <span>没有符合条件的资料。</span>
          </div>
        )}
      </div>

      <input
        ref={fileInput}
        type="file"
        accept=".txt,.md,.pdf"
        hidden
        onChange={(event) => {
          onUpdate(event.target.files?.[0], target.current as Document);
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
