"use client";

import { KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { api, type ApiError, type Source } from "@/lib/api";
import styles from "./source-viewer.module.css";

export type SourceState = "AVAILABLE" | "DOCUMENT_DELETED" | "VERSION_EXPIRED";
export type PreviewSource = Source & { state?: SourceState };
type Props = { source: PreviewSource; documentName: string; onClose: () => void };
type Preview = { key: string } & (
  | { kind: "loading" }
  | { kind: "text"; text: string }
  | { kind: "pdf"; url: string }
  | { kind: "error" | "unavailable"; message: string }
);

const unavailableMessages = {
  DOCUMENT_DELETED: "资料已删除，无法查看原文。",
  VERSION_EXPIRED: "此历史版本已过期，无法查看原文。",
};

function errorMessage(error: unknown) {
  const status = (error as ApiError)?.status;
  if (status === 401) return "登录已过期，请重新登录后重试。";
  if (status === 404) return "来源已删除或版本已失效，请返回历史记录确认。";
  return "原文暂时无法载入，请重试。";
}

export default function SourceViewer({ source, documentName, onClose }: Props) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [attempt, setAttempt] = useState(0);
  const sourceKey = `${source.source_id}:${source.content_version_id}`;
  const [preview, setPreview] = useState<Preview>({ key: sourceKey, kind: "loading" });
  const { source_id: sourceId, document_id: documentId, content_version_id: versionId, quote } = source;
  const state = source.state ?? "AVAILABLE";
  const start = source.locator?.start;
  const end = source.locator?.end;

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []);

  useEffect(() => {
    if (state !== "AVAILABLE") return;
    const controller = new AbortController();
    let active = true;
    let objectUrl: string | undefined;
    (async () => {
      try {
        const current = await api<PreviewSource>(`sources/${sourceId}`, { signal: controller.signal });
        if (!active) return;
        if (current.state && current.state !== "AVAILABLE") {
          setPreview({ key: sourceKey, kind: "unavailable", message: unavailableMessages[current.state] });
          return;
        }
        if (current.document_id !== documentId || current.content_version_id !== versionId) {
          setPreview({ key: sourceKey, kind: "unavailable", message: "来源版本已失效，请返回历史记录确认。" });
          return;
        }
        const response = await fetch(`/api/v1/documents/${documentId}/contents/${versionId}/file`, {
          credentials: "same-origin", cache: "no-store", signal: controller.signal,
        });
        if (!response.ok) throw Object.assign(new Error(), { status: response.status });
        const contentType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
        if (contentType === "application/pdf") {
          const blob = await response.blob();
          if (!active) return;
          objectUrl = URL.createObjectURL(blob);
          setPreview({ key: sourceKey, kind: "pdf", url: objectUrl });
        } else {
          const text = await response.text();
          if (!active) return;
          const excerpt = start != null && end != null ? Array.from(text).slice(start, end).join("") : quote;
          setPreview({ key: sourceKey, kind: "text", text: excerpt || quote || "未提供定位内容。" });
        }
      } catch (error) {
        if (active) setPreview({ key: sourceKey, kind: "error", message: errorMessage(error) });
      }
    })();
    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [sourceKey, sourceId, documentId, versionId, state, start, end, quote, attempt]);

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
    if (event.key !== "Tab") return;
    const controls = dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])');
    if (!controls?.length) return;
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  const current = preview.key === sourceKey ? preview : { key: sourceKey, kind: "loading" as const };
  const unavailable = state !== "AVAILABLE" ? unavailableMessages[state] : current.kind === "unavailable" ? current.message : null;
  const page = source.locator?.page ?? 1;
  return (
    <div className={styles.backdrop} role="presentation" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section ref={dialogRef} className={styles.viewer} role="dialog" aria-modal="true" aria-label="原文依据" aria-describedby={titleId} onKeyDown={handleKeyDown}>
        <header><div><span className={styles.eyebrow}>SOURCE EXCERPT</span><h2 id={titleId}>{documentName}</h2></div><button ref={closeRef} type="button" aria-label="关闭原文" onClick={onClose}>×</button></header>
        {unavailable ? <div className={styles.feedback}><p role="status">{unavailable}</p><button type="button" disabled>预览不可用</button></div> : <>
          {quote && <blockquote>{quote}</blockquote>}
          {current.kind === "loading" && <p className={styles.feedback} role="status">正在载入原文…</p>}
          {current.kind === "error" && <div className={styles.feedback}><p role="alert">{current.message}</p><button type="button" onClick={() => { setPreview({ key: sourceKey, kind: "loading" }); setAttempt((value) => value + 1); }}>重新载入原文</button></div>}
          {current.kind === "text" && <pre>{current.text}</pre>}
          {current.kind === "pdf" && <><a className={styles.pdfLink} href={`${current.url}#page=${page}`} target="_blank" rel="noopener noreferrer">在新窗口打开 PDF 原文（第 {page} 页）</a><iframe tabIndex={-1} title={`${documentName} PDF 原文`} src={`${current.url}#page=${page}`} /></>}
        </>}
      </section>
    </div>
  );
}
