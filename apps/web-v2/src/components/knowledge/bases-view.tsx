"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, Folder, Plus, Search, Trash2 } from "lucide-react";
import { useKnowledgeContext, useQuestionsContext } from "@/components/workspace/workspace-provider";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonRows } from "@/components/ui/skeleton";
import { relativeTime } from "@/lib/format";
import { useQueryState } from "@/lib/query-state";
import type { KnowledgeBase } from "@/services/api";
import styles from "./knowledge.module.css";

export function BasesView() {
  const router = useRouter();
  const knowledge = useKnowledgeContext();
  const questions = useQuestionsContext();
  const [query, setQuery] = useQueryState("q", "", 200);
  const [pending, setPending] = useState<KnowledgeBase | null>(null);

  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase();
    return value ? knowledge.bases.filter((base) => base.name.toLowerCase().includes(value)) : knowledge.bases;
  }, [knowledge.bases, query]);

  const hasBases = knowledge.bases.length > 0;

  function focusCreate() {
    const input = document.getElementById("new-base-name");
    const group = input?.closest("details");
    if (group) group.open = true;
    input?.focus();
  }

  async function remove() {
    if (!pending) return;
    const outcome = await knowledge.remove(pending.id);
    setPending(null);
    if (outcome === "stale") return;
    if (outcome === "ok") {
      toast.success(`已删除「${pending.name}」`);
      router.push("/knowledge-bases");
    } else {
      toast.error("知识库未能删除，请稍后重试。");
    }
  }

  return (
    <div className={styles.page} data-entrance="cards">
      <header className="workspace-header">
        <div>
          <p className={styles.eyebrow}>Knowledge bases</p>
          <h1>{hasBases ? "我的知识库" : "开始整理你的资料"}</h1>
          <p className={styles.pageLead}>
            {hasBases
              ? `共 ${knowledge.bases.length} 个知识库 · ${questions.history.length} 条问答记录。选择一个知识库查看资料与索引状态。`
              : "先建立一个知识库，再上传 TXT、Markdown 或可读取文本的 PDF。索引就绪后即可带着原文引用提问。"}
          </p>
        </div>
        <Button onClick={focusCreate}>
          <Plus size={15} aria-hidden="true" /> 新建知识库
        </Button>
      </header>

      <div className={styles.toolbar}>
        <label className={styles.search}>
          <Search size={14} aria-hidden="true" />
          <input
            aria-label="搜索知识库"
            name="q"
            autoComplete="off"
            spellCheck={false}
            placeholder="搜索知识库名称…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <span className={styles.toolbarMeta}>{filtered.length} 个结果</span>
      </div>

      {knowledge.loading && !knowledge.bases.length ? (
        <SkeletonRows rows={4} />
      ) : filtered.length ? (
        <div className={styles.baseGrid}>
          {filtered.map((base, index) => (
            <article className={styles.baseCard} key={base.id} style={index < 4 ? { animationDelay: `${[0, 40, 70, 95][index]}ms` } : undefined}>
              <Link className={styles.baseCardLink} href={`/knowledge-bases/${base.id}`} prefetch={false}>
                <span className={styles.baseCover} data-tone={Array.from(base.id).reduce((sum, char) => sum + char.charCodeAt(0), 0) % 3} aria-hidden="true">
                  <span className={styles.baseCardIcon}>
                    <Folder size={19} strokeWidth={1.5} aria-hidden="true" />
                  </span>
                </span>
                <span className={styles.baseCardText}>
                  <strong>{base.name}</strong>
                </span>
                <span className={styles.baseCardFoot}>
                  <span>{base.updated_at ? `更新于 ${relativeTime(base.updated_at)}` : "查看资料与索引状态"}</span>
                  <span className={styles.baseOpen}>打开 <ArrowRight size={15} className={styles.baseCardArrow} aria-hidden="true" /></span>
                </span>
              </Link>
              <button
                className={styles.baseCardDelete}
                aria-label={`删除知识库 ${base.name}`}
                title="删除知识库"
                onClick={() => setPending(base)}
              >
                <Trash2 size={14} />
              </button>
            </article>
          ))}
          {!query && <button className={styles.baseCreate} aria-label="在网格中新建知识库" onClick={focusCreate}>
            <span className={styles.createTile} aria-hidden="true"><Plus size={24} strokeWidth={1.4} /></span>
            <strong>新建知识库</strong>
            <span>为下一组资料留一个位置</span>
          </button>}
        </div>
      ) : query ? (
        <EmptyState
          title="没有匹配的知识库"
          description={`没有找到包含“${query.trim()}”的知识库，换个关键词试试。`}
          action={<Button variant="secondary" size="sm" onClick={() => setQuery("")}>清除搜索</Button>}
        />
      ) : (
        <EmptyState
          illustration
          icon={<Folder size={20} strokeWidth={1.5} />}
          title="这里还没有知识库"
          description="创建第一个知识库，上传资料并等待索引就绪。之后每次提问都会附带可核验的原文来源。"
          action={<Button onClick={focusCreate}>创建第一个知识库</Button>}
        />
      )}

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => { if (!open) setPending(null); }}
        title={`删除「${pending?.name ?? ""}」？`}
        description="知识库及其中的资料会立即对所有问答不可见，删除后无法恢复。此操作不会影响其他知识库。"
        onConfirm={() => void remove()}
        busy={knowledge.working}
      />
    </div>
  );
}
