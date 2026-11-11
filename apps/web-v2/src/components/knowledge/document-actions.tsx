"use client";

import dynamic from "next/dynamic";
import { useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import type { Document } from "@/services/api";
import styles from "./knowledge.module.css";

let pending: Promise<typeof import("./document-actions-menu")> | undefined;
const loadMenu = () => pending ??= import("./document-actions-menu").catch((error: unknown) => { pending = undefined; throw error; });
const Menu = dynamic(loadMenu, { ssr: false });

export type DocumentActionsProps = {
  document: Document; busy: boolean;
  onUpdate: (document: Document) => void;
  onRebuild: (document: Document) => void;
  onDelete: (document: Document) => void;
};

/** Preload on intent; reading a large list doesn't download the menu engine. */
export function DocumentActions(props: DocumentActionsProps) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [initialFocus, setInitialFocus] = useState<"first" | "last" | undefined>();
  const intent = useRef(0);
  const preload = () => { void loadMenu().catch(() => {}); };
  async function show(edge?: "first" | "last") {
    if (props.busy || loading) return;
    const token = ++intent.current;
    setLoading(true); setError(false); setInitialFocus(edge);
    try { await loadMenu(); if (token === intent.current) { setLoaded(true); setOpen(true); } }
    catch { if (token === intent.current) setError(true); }
    finally { if (token === intent.current) setLoading(false); }
  }
  if (loaded) return <Menu {...props} open={open} onOpenChange={setOpen} initialFocus={initialFocus} />;
  return (
    <div className={styles.docMenu}>
      <button type="button" aria-label={`${props.document.original_name} 操作`} aria-haspopup="menu" aria-expanded={false} aria-busy={loading} disabled={props.busy} onPointerEnter={preload} onFocus={preload} onClick={(event) => void show(event.detail === 0 ? "first" : undefined)} onKeyDown={(event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); void show(event.key === "ArrowUp" ? "last" : "first"); }
        if (event.key === "Escape") { intent.current++; setLoading(false); }
      }}>
        <MoreHorizontal size={18} aria-hidden="true" />
      </button>
      {error && <span role="alert">操作菜单未能载入，请重试。</span>}
    </div>
  );
}
