"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, FileText, Layers } from "lucide-react";
import { api, type Document, type KnowledgeBase } from "@/services/api";
import { messageOf } from "@/lib/format";
import { useQueryState } from "@/lib/query-state";
import { useKnowledgeContext, useDocumentsContext } from "@/components/workspace/workspace-provider";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonRows } from "@/components/ui/skeleton";
import { UploadZone } from "./upload-zone";
import { FilePicker } from "@/components/ui/file-picker";
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
  const knowledge = useKnowledgeContext();
  const documents = useDocumentsContext();
  const [remote, setRemote] = useState<KnowledgeBase | null>(null);
  const [error, setError] = useState("");
  const [statusParam, setStatus] = useQueryState("status", "all");
  const filter: Filter = filters.some((item) => item.key === statusParam) ? statusParam as Filter : "all";
  const selected = useRef("");
  const selectBase = knowledge.selectBase;

  useEffect(() => {
    if (!baseId) return;
    if (selected.current !== baseId) {
      selected.current = baseId;
      selectBase(baseId);
    }
    let active = true;
    const controller = new AbortController();
    void (async () => {
      await Promise.resolve();
      if (!active) return;
      setError("");
      try {
        const base = await api<KnowledgeBase>(`knowledge-bases/${encodeURIComponent(baseId)}`, { signal: controller.signal });
        if (active) setRemote(base);
      } catch (reason) {
        if (active) setError(messageOf(reason));
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [baseId, selectBase]);

  const base = knowledge.bases.find((item) => item.id === baseId) ?? (remote?.id === baseId ? remote : null);
  const readyCount = documents.documents.filter((document) => document.status === "READY").length;
  const visible = useMemo(() => documents.documents.filter((document) => matches(document, filter)), [documents.documents, filter]);
  const counts = Object.fromEntries(filters.map(({ key }) => [key, documents.documents.filter((document) => matches(document, key)).length])) as Record<Filter, number>;

  async function upload(file: File | undefined, target?: Document) {
    if (!file) return;
    const outcome = await documents.upload(file, target);
    if (outcome === "stale") return;
    if (outcome === "accepted") {
      toast.success(target ? "已接受更新，索引状态见资料列表" : "文件已接受，索引状态见资料列表");
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
    <div className={styles.page}>
      <Link className={styles.back} href="/knowledge-bases">
        <ArrowLeft size={16} aria-hidden="true" /> 全部知识库
      </Link>

      {error ? (
        <p className={styles.statusMessage} role="status">{error}</p>
      ) : (
        <>
          <header className="workspace-header">
            <div>
              <p className={styles.eyebrow}>Knowledge base</p>
              <h1>{base?.name ?? "知识库"}</h1>
              <p className={styles.pageLead}>
                {documents.refreshing && !documents.documents.length
                  ? "正在读取资料…"
                  : `${documents.documents.length} 份资料 · ${readyCount} 份可用于问答`}
              </p>
            </div>
            <span className={styles.detailBadge} data-header-tag>
              <Layers size={16} aria-hidden="true" /> 私有空间
            </span>
          </header>

          <dl className={styles.statRow} aria-label={documents.hasMore ? "已加载资料统计" : "资料统计"}>
            {filters.map(({ key, label }) => <div className={styles.stat} key={key} data-state={key}>
              <dt>{label}</dt>
              <dd>{documents.refreshing && !documents.documents.length ? "—" : counts[key]}</dd>
            </div>)}
          </dl>
          {documents.hasMore && <p className={styles.partialCounts}>以上为已加载资料的数量，可继续加载更多。</p>}

          <UploadZone
            disabled={!baseId || Boolean(error)}
            busy={documents.working}
            onUpload={(file) => void upload(file)}
          />

          <div className={styles.filterRow} role="group" aria-label="筛选资料">
            <span className={styles.filterIndicator} style={{ transform: `translateX(${filters.findIndex((item) => item.key === filter) * 100}%)` }} aria-hidden="true" />
            {filters.map(({ key, label }) => (
              <button
                key={key}
                className={filter === key ? `${styles.filter} ${styles.filterActive}` : styles.filter}
                aria-pressed={filter === key}
                onClick={() => setStatus(key)}
              >
                {label}
                <span>
                  {counts[key]}
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
              illustration={!documents.documents.length ? "documents" : false}
              icon={<FileText size={20} strokeWidth={1.5} />}
              title={documents.documents.length ? "这个筛选下没有资料" : "还没有资料"}
              description={documents.documents.length
                ? "切换到“全部”查看其他状态的资料。"
                : "上传第一份资料，等待索引显示“已就绪”后即可提问。支持 TXT、Markdown 与可读取文本的 PDF。"}
              action={documents.documents.length
                ? undefined
                : <FilePicker label="选择文件" className={styles.emptyUpload} disabled={!baseId || documents.working} onPick={(file) => void upload(file)} /> }
            />
          )}

          {documents.hasMore && (
            <button className={styles.loadMore} onClick={() => void documents.loadMore()} disabled={documents.loadingMore}>
              加载更多资料
            </button>
          )}
          <p className={styles.detailFootnote}>资料仅自己可见 · 只有已就绪的资料会参与检索与问答</p>
        </>
      )}
    </div>
  );
}
