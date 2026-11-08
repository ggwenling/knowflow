"use client";

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
  onCreateBase,
  onFocusComposer,
}: {
  bases: KnowledgeBase[];
  selectedBase: string;
  documentCount?: number;
  moreDocuments: boolean;
  history: QuestionHistory[];
  loading: boolean;
  onCreateBase: () => void;
  onFocusComposer: () => void;
}) {
  return (
    <div className={styles.overview}>
      <section className={styles.panel} aria-labelledby="base-preview">
        <div className={styles.panelHead}>
          <h2 id="base-preview">我的知识库</h2>
          <Link href="/knowledge-bases" aria-label="查看全部知识库">
            查看全部 <ArrowRight size={15} aria-hidden="true" />
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
                  <Link className={styles.baseLink} href={`/knowledge-bases/${base.id}`}>
                    <span className={styles.rowIcon}>
                      <Folder size={20} strokeWidth={1.5} aria-hidden="true" />
                    </span>
                    <span className={styles.baseText}>
                      <strong>{base.name}</strong>
                      <small>{base.updated_at ? `更新于 ${relativeTime(base.updated_at)}` : "查看知识库文档"}</small>
                    </span>
                    {count && <span className={styles.count}>{count}</span>}
                    <ArrowRight className={styles.rowArrow} size={15} strokeWidth={1.5} aria-hidden="true" />
                  </Link>
                </div>
              );
            })}
          </div>
        ) : (
          <div className={styles.empty}>
            <Folder size={26} strokeWidth={1.4} aria-hidden="true" />
            <p>这里还没有知识库。</p>
            <button onClick={onCreateBase}>创建第一个知识库 <ArrowRight size={14} aria-hidden="true" /></button>
          </div>
        )}
      </section>

      <section className={styles.panel} aria-labelledby="recent-preview">
        <div className={styles.panelHead}>
          <h2 id="recent-preview">最近问答</h2>
          <Link href="/conversations" aria-label="查看全部对话">
            查看全部 <ArrowRight size={15} aria-hidden="true" />
          </Link>
        </div>
        {history.length ? (
          <div className={styles.historyList}>
            {history.slice(0, 3).map((item) => (
              <Link className={styles.conversation} key={item.question_id} href={`/conversations/${item.question_id}`}>
                <span className={styles.rowIcon}>
                  <MessageSquare size={19} strokeWidth={1.5} aria-hidden="true" />
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
            <MessageSquare size={26} strokeWidth={1.4} aria-hidden="true" />
            <p>还没有对话，开始提问吧。</p>
            <button onClick={onFocusComposer}>向知识库提问 <ArrowRight size={14} aria-hidden="true" /></button>
          </div>
        )}
      </section>
    </div>
  );
}
