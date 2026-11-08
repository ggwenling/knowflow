"use client";

import { useEffect, useState } from "react";
import { api, apiFetch, type ApiError, type Source } from "@/services/api";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import styles from "./chat.module.css";
import { sliceCodePoints } from "@/lib/text-range";

type SourceWithState = Source & { state?: "AVAILABLE" | "DOCUMENT_DELETED" | "VERSION_EXPIRED" };
type Preview =
  | { kind: "loading" }
  | { kind: "text"; text: string }
  | { kind: "pdf"; url: string }
  | { kind: "unavailable" | "error"; message: string };

const unavailableMessages: Record<string, string> = {
  DOCUMENT_DELETED: "资料已删除，无法查看原文。",
  VERSION_EXPIRED: "此历史版本已过期，无法查看原文。",
};

function errorMessage(error: unknown) {
  const status = (error as ApiError)?.status;
  if (status === 401) return "登录已过期，请重新登录后重试。";
  if (status === 404) return "来源已删除或版本已失效，请返回历史记录确认。";
  return "原文暂时无法载入，请重试。";
}

export function SourceDialog({
  source,
  documentName,
  open,
  onOpenChange,
  returnFocus,
}: {
  source: Source | null;
  documentName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  returnFocus?: HTMLElement | null;
}) {
  const [preview, setPreview] = useState<Preview>({ kind: "loading" });
  const sourceKey = source ? `${source.source_id}:${source.content_version_id}` : "";
  const page = source?.locator?.page ?? 1;

  useEffect(() => {
    if (!open || !source) return;
    const controller = new AbortController();
    let active = true;
    let objectUrl: string | undefined;

    (async () => {
      await Promise.resolve();
      if (!active) return;
      setPreview({ kind: "loading" });
      try {
        const current = await api<SourceWithState>(`sources/${encodeURIComponent(source.source_id)}`, {
          signal: controller.signal,
        });
        if (!active) return;
        if (current.state && current.state !== "AVAILABLE") {
          setPreview({ kind: "unavailable", message: unavailableMessages[current.state] ?? "来源当前不可用。" });
          return;
        }
        if (current.document_id !== source.document_id || current.content_version_id !== source.content_version_id) {
          setPreview({ kind: "unavailable", message: "来源版本已失效，请返回历史记录确认。" });
          return;
        }
        const filePath = `documents/${encodeURIComponent(source.document_id)}/contents/${encodeURIComponent(source.content_version_id)}/file`;
        // The frozen source locator identifies the historical version's format.
        // PDF goes straight to the native viewer, preserving its Range requests.
        if (source.locator?.kind === "pdf_page" || current.locator?.kind === "pdf_page") {
          setPreview({ kind: "pdf", url: `/api/v1/${filePath}#page=${page}` });
          return;
        }
        const response = await apiFetch(
          filePath,
          { credentials: "same-origin", cache: "no-store", signal: controller.signal },
        );
        if (!response.ok) throw Object.assign(new Error(), { status: response.status });
        const contentType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
        if (contentType === "application/pdf") {
          // Legacy/missing locators still use the one response already fetched.
          const blob = await response.blob();
          if (!active) return;
          objectUrl = URL.createObjectURL(blob);
          setPreview({ kind: "pdf", url: `${objectUrl}#page=${page}` });
          return;
        }
        const text = await response.text();
        if (!active) return;
        const start = source.locator?.start;
        const end = source.locator?.end;
        const excerpt = start != null && end != null ? sliceCodePoints(text, start, end) : source.quote;
        setPreview({ kind: "text", text: excerpt || source.quote || "未提供定位内容。" });
      } catch (error) {
        if (active) setPreview({ kind: "error", message: errorMessage(error) });
      }
    })();

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [open, source, page, sourceKey]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        size="lg"
        showClose={false}
        className={styles.sourceDialog}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          returnFocus?.focus();
        }}
      >
        <DialogClose aria-label="关闭原文" className={styles.sourceClose}>×</DialogClose>
        <header className={styles.sourceHead}>
          <p className={styles.eyebrow}>Source excerpt</p>
          <DialogTitle className={styles.sourceTitle}>原文依据</DialogTitle>
          <DialogDescription className={styles.sourceDescription}>
            {documentName}{source?.locator?.page ? ` · 第 ${source.locator.page} 页` : ""}
          </DialogDescription>
        </header>

        {source?.quote && <blockquote className={styles.sourceQuote}>{source.quote}</blockquote>}

        {preview.kind === "loading" && <p className={styles.sourceFeedback} role="status">正在载入原文…</p>}
        {preview.kind === "unavailable" && <p className={styles.sourceFeedback} role="status">{preview.message}</p>}
        {preview.kind === "error" && <p className={styles.sourceFeedback} role="alert">{preview.message}</p>}
        {preview.kind === "text" && <pre className={styles.sourcePre}>{preview.text}</pre>}
        {preview.kind === "pdf" && (
          <>
            <a className={styles.docsLink} href={preview.url} target="_blank" rel="noopener noreferrer">在新窗口打开 PDF 原文</a>
            <iframe className={styles.sourceFrame} title={`${documentName} PDF 原文`} src={preview.url} />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
