"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { ArrowLeft, FileText, Layers } from "lucide-react";
import { api, type Document, type KnowledgeBase } from "@/services/api";
import { messageOf } from "@/lib/format";
import { useQueryState } from "@/lib/query-state";
import { useWorkspaceDataContext } from "@/components/workspace/workspace-provider";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonRows } from "@/components/ui/skeleton";
import { UploadZone } from "./upload-zone";
import { DocumentList } from "./document-list";
import styles from "./knowledge.module.css";

type Filter = "all" | "ready" | "working" | "failed";
const filters: { key: Filter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "ready", label: "已就绪" },
  { key: "working", label: "处理中" },
  { key: "failed", label: "失败" },
];

function matches(document: Document, filter: Filter) {
  const status = document.status.toUpperCase();
  if (filter === "ready") return status === "READY";
  if (filter === "failed") return status === "FAILED" || status === "CANCELLED";
  if (filter === "working") return ["QUEUED", "RUNNING", "PROCESSING"].includes(status);
  return true;
}

export function BaseDetailView() {
  const params = useParams<{ baseId: string }>();
  const baseId = params?.baseId ?? "";
  const reduce = useReducedMotion();
  const { knowledge, documents } = useWorkspaceDataContext();
  const [remote, setRemote] = useState<KnowledgeBase | null>(null);
  const [error, setError] = useState("");
  const [statusParam, setStatus] = useQueryState("status", "all");
  const filter: Filter = filters.some((item) => item.key === statusParam) ? statusParam as Filter : "all";
  const selected = useRef("");

  useEffect(() => {
    if (!baseId) return;
    if (selected.current !== baseId) {
      selected.current = baseId;
      knowledge.selectBase(baseId);
    }
    let active = true;
    void (async () => {
      await Promise.resolve();
      setError("");
      try {
        const base = await api<KnowledgeBase>(`knowledge-bases/${encodeURIComponent(baseId)}`);
        if (active) setRemote(base);
      } catch (reason) {
        if (active) setError(messageOf(reason));
      }
    })();
    return () => {
      active = false;
    };
    // knowledge.selectBase is stable; re-running on the whole context would refetch on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseId]);

  const base = knowledge.bases.find((item) => item.id === baseId) ?? remote;
  const readyCount = documents.documents.filter((document) => document.status === "READY").length;
  const visible = useMemo(() => documents.documents.filter((document) => matches(document, filter)), [documents.documents, filter]);

  async function upload(file: File | undefined, target?: Document) {
    if (!file) return;
    const outcome = await documents.upload(file, target);
    if (outcome === "stale") return;
    if (outcome === "ok") {
      toast.success(target ? "已提交更新，索引完成后生效" : "已上传，正在建立索引");
    } else {
      toast.error("上传未能完成，请检查文件后重试。");
    }
  }

  async function remove(document: Document) {
    const outcome = await documents.remove(document);
    if (outcome === "stale") return;
    if (outcome === "ok") toast.success(`已删除「${document.original_name}」`);
    else toast.error("资料未能删除，请稍后重试。");
  }

  return (
    <motion.div
      className={styles.page}
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.26 }}
    >
      <Link className={styles.back} href="/knowledge-bases">
        <ArrowLeft size={14} aria-hidden="true" /> 全部知识库
      </Link>

      {error ? (
        <p className={styles.statusMessage} role="status">{error}</p>
      ) : (
        <>
          <header className={styles.detailHead}>
            <div>
              <p className={styles.eyebrow}>Knowledge base</p>
              <h1>{base?.name ?? "知识库"}</h1>
              <p className={styles.pageLead}>
                {documents.refreshing && !documents.documents.length
                  ? "正在读取资料…"
                  : `${documents.documents.length} 份资料 · ${readyCount} 份可用于问答`}
              </p>
            </div>
            <span className={styles.detailBadge}>
              <Layers size={14} aria-hidden="true" /> 私有空间
            </span>
          </header>

          <UploadZone
            disabled={!baseId || Boolean(error)}
            busy={documents.working}
            onUpload={(file) => void upload(file)}
          />

          <div className={styles.filterRow} role="group" aria-label="筛选资料">
            {filters.map(({ key, label }) => (
              <button
                key={key}
                className={filter === key ? `${styles.filter} ${styles.filterActive}` : styles.filter}
                aria-pressed={filter === key}
                onClick={() => setStatus(key)}
              >
                {label}
                <span>
                  {key === "all" ? documents.documents.length : documents.documents.filter((document) => matches(document, key)).length}
                </span>
              </button>
            ))}
            <span className={styles.filterSpacer} />
            {documents.refreshing && <span className={styles.syncing}>同步中…</span>}
          </div>

          {documents.notice && (
            <div className={styles.statusMessage} role="status">
              {documents.notice}
              <button onClick={documents.clearNotice}>关闭</button>
            </div>
          )}

          {documents.refreshing && !documents.documents.length ? (
            <SkeletonRows rows={4} />
          ) : visible.length ? (
            <DocumentList
              documents={visible}
              busy={documents.working}
              onUpdate={(file, document) => void upload(file, document)}
              onRebuild={(document) => {
                void documents.rebuild(document).then((outcome) => {
                  if (outcome === "stale") return;
                  if (outcome === "ok") toast.success("已开始重建索引");
                  else toast.error("重建未能开始，请稍后重试。");
                });
              }}
              onDelete={remove}
            />
          ) : (
            <EmptyState
              icon={<FileText size={20} strokeWidth={1.5} />}
              title={documents.documents.length ? "这个筛选下没有资料" : "还没有资料"}
              description={documents.documents.length
                ? "切换到“全部”查看其他状态的资料。"
                : "上传第一份资料，等待索引显示“已就绪”后即可提问。支持 TXT、Markdown 与可读取文本的 PDF。"}
              action={documents.documents.length
                ? undefined
                : <label className={styles.emptyUpload}>选择文件<input type="file" accept=".txt,.md,.pdf" disabled={!baseId || documents.working} onChange={(event) => { void upload(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>}
            />
          )}

          {documents.hasMore && (
            <button className={styles.loadMore} onClick={() => void documents.loadMore()} disabled={documents.loadingMore}>
              加载更多资料
            </button>
          )}
        </>
      )}
    </motion.div>
  );
}
