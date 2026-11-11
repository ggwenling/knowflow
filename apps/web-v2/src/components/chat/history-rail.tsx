"use client";

import Link from "next/link";
import { Fragment, useMemo } from "react";
import { ArrowRight, Plus, Search } from "lucide-react";
import type { QuestionHistory } from "@/services/api";
import { groupQuestions, questionStatusLabel } from "@/lib/format";
import { useQueryState } from "@/lib/query-state";
import { SkeletonRows } from "@/components/ui/skeleton";
import styles from "./chat.module.css";

type Props = {
  items: QuestionHistory[];
  loading: boolean;
  hasMore: boolean;
  activeId?: string;
  onLoadMore: () => void;
  onNew: () => void;
  onNavigate?: () => void;
};

export function HistoryRail({ items, loading, hasMore, activeId, onLoadMore, onNew, onNavigate }: Props) {
  const [query, setQuery] = useQueryState("history", "", 200);
  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return items;
    return items.filter((item) => item.question.toLowerCase().includes(value));
  }, [items, query]);
  const groups = useMemo(() => groupQuestions(filtered), [filtered]);

  return (
    <div className={styles.rail}>
      <div className={styles.railHead}>
        <div>
          <p className={styles.eyebrow}>History</p>
          <h2>对话历史</h2>
        </div>
        <button className={styles.newChat} onClick={onNew} aria-label="新建对话">
          <Plus size={16} aria-hidden="true" />
        </button>
      </div>
      <label className={styles.search} data-composite-field>
        <Search size={16} aria-hidden="true" />
        <input
          aria-label="搜索对话历史"
          name="history"
          autoComplete="off"
          spellCheck={false}
          placeholder="搜索问题…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>

      <div className={styles.historyScroll}>
        {loading && !items.length ? <SkeletonRows rows={5} /> : null}
        {!loading && !filtered.length ? (
          <p className={styles.railEmpty}>{query ? "没有匹配的对话。" : "还没有对话记录。"}</p>
        ) : null}
        {groups.map((group) => (
          <Fragment key={group.label}>
            <p className={styles.groupLabel}>{group.label}</p>
            {group.items.map((item) => (
              <Link
                key={item.question_id}
                className={activeId === item.question_id ? `${styles.historyButton} ${styles.historyActive}` : styles.historyButton}
                href={`/conversations/${item.question_id}`}
                prefetch={false}
                onClick={onNavigate}
              >
                <span>{item.question}</span>
                <small>{questionStatusLabel(item.status)}</small>
              </Link>
            ))}
          </Fragment>
        ))}
        {hasMore && query ? <p className={styles.railEmpty} role="status">正在搜索已加载的记录，可加载更多继续查找。</p> : null}
        {hasMore ? (
          <button className={styles.loadMore} onClick={onLoadMore} disabled={loading}>
            加载更多问答
          </button>
        ) : null}
      </div>

      <div className={styles.railFoot}>
        <ArrowRight size={16} aria-hidden="true" />
        <span>单轮问答 · 每次提问独立检索</span>
      </div>
    </div>
  );
}
