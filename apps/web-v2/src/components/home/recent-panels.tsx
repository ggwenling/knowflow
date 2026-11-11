"use client";

import { StaticArt } from "@/components/ui/static-art";
import Link from "next/link";
import { ArrowRight, Folder, MessageSquare } from "lucide-react";
import type { KnowledgeBase, QuestionHistory } from "@/services/api";
import { questionStatusLabel, relativeTime } from "@/lib/format";
import { SkeletonRows } from "@/components/ui/skeleton";
import styles from "./home-view.module.css";

export function RecentPanels({
  bases,
  selectedBase,
  documentCount,
  moreDocuments,
  history,
  loading,
  onFocusComposer,
}: {
  bases: KnowledgeBase[];
  selectedBase: string;
  documentCount?: number;
  moreDocuments: boolean;
  history: QuestionHistory[];
  loading: boolean;
  onFocusComposer: () => void;
}) {
  return (
    <div className={styles.overview}>
      <section className={styles.panel} aria-labelledby="base-preview">
        <div className={styles.panelHead}>
          <h2 data-display-heading id="base-preview">我的知识库</h2>
          <Link href="/knowledge-bases" aria-label="查看全部知识库">
            查看全部 <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
        {loading && !bases.length ? (
          <SkeletonRows rows={3} />
        ) : bases.length ? (
          <div className={styles.baseList}>
            {bases.slice(0, 3).map((base) => {
              const count = base.id === selectedBase && documentCount != null
                ? `${moreDocuments ? "已加载 " : ""}${documentCount} 个文档`
                : "";
              return (
                <div className={styles.baseRow} key={base.id}>
                  <Link className={styles.baseLink} href={`/knowledge-bases/${base.id}`} prefetch={false}>
                    <span className={styles.rowIcon}>
                      <Folder size={20} strokeWidth={1.5} aria-hidden="true" />
                    </span>
                    <span className={styles.baseText}>
                      <strong>{base.name}</strong>
                      <small>{base.updated_at ? `更新于 ${relativeTime(base.updated_at)}` : "查看知识库文档"}</small>
                    </span>
                    {count && <span className={styles.count}>{count}</span>}
                    <ArrowRight className={styles.rowArrow} size={16} strokeWidth={1.5} aria-hidden="true" />
                  </Link>
                </div>
              );
            })}
          </div>
        ) : (
          <div className={styles.empty}>
            <StaticArt src="/atlas-empty-bases.webp?v=monochrome-d" alt="" width={108} height={72} loading="lazy" />
            <p>这里还没有知识库。</p>
            <Link href="/knowledge-bases?create=1">创建第一个知识库 <ArrowRight size={16} aria-hidden="true" /></Link>
          </div>
        )}
      </section>

      <section className={styles.panel} aria-labelledby="recent-preview">
        <div className={styles.panelHead}>
          <h2 data-display-heading id="recent-preview">最近问答</h2>
          <Link href="/conversations" aria-label="查看全部对话">
            查看全部 <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
        {history.length ? (
          <div className={styles.historyList}>
            {history.slice(0, 3).map((item) => (
              <Link className={styles.conversation} key={item.question_id} href={`/conversations/${item.question_id}`} prefetch={false}>
                <span className={styles.rowIcon}>
                  <MessageSquare size={20} strokeWidth={1.5} aria-hidden="true" />
                </span>
                <span className={styles.conversationText}>
                  <strong>{item.question}</strong>
                  <small>{item.finished_at ? relativeTime(item.finished_at) : "进行中"}</small>
                </span>
                <span className={styles.status}>{questionStatusLabel(item.status)}</span>
              </Link>
            ))}
          </div>
        ) : (
          <div className={styles.empty}>
            <StaticArt src="/atlas-empty-history.webp?v=monochrome-d" alt="" width={108} height={72} loading="lazy" />
            <p>还没有对话，开始提问吧。</p>
            <button onClick={onFocusComposer}>向知识库提问 <ArrowRight size={16} aria-hidden="true" /></button>
          </div>
        )}
      </section>
    </div>
  );
}
