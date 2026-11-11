"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { OnDemand } from "@/components/ui/on-demand";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CircleHelp, FileText, FolderOpen, Layers, PanelLeft, PanelRight, Plus } from "lucide-react";
import { useKnowledgeContext, useDocumentsContext, useQuestionsContext, useStreamControls } from "@/components/workspace/workspace-provider";
import { useDraftActions } from "@/components/store";
import { Button } from "@/components/ui/button";
import { FilePicker } from "@/components/ui/file-picker";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatBytes, formatLabel } from "@/lib/format";
import type { Source } from "@/services/api";
import { HistoryRail } from "./history-rail";
import { AnswerPanel } from "./answer-panel";
import { Composer } from "./composer";
import { CurrentSources } from "./current-sources";
import styles from "./chat.module.css";

const SourceDialog = dynamic(() => import("./source-dialog").then((module) => module.SourceDialog), { ssr: false });
const MobilePanel = dynamic(() => import("./mobile-panel").then((module) => module.MobilePanel), { ssr: false });

function DocumentsPanel({ onOpenSource }: { onOpenSource: (source: Source, documentName: string, trigger: HTMLButtonElement) => void }) {
  const documents = useDocumentsContext();
  const knowledge = useKnowledgeContext();
  const selected = knowledge.bases.find((base) => base.id === knowledge.selectedBase);

  return (
    <div className={styles.docs}>
      <div className={styles.docsHead}>
        <div>
          <p className={styles.eyebrow}>Documents</p>
          <h2 data-display-heading>资料 <span>{documents.documents.length}</span></h2>
        </div>
        <FilePicker label="上传资料" className={styles.uploadChip} disabled={!knowledge.selectedBase || documents.working} onPick={(file) => void documents.upload(file)}>
          <Plus size={16} aria-hidden="true" />
        </FilePicker>
      </div>

      <p className={styles.docsHint}>
        {selected ? `${selected.name} · ${documents.documents.filter((item) => item.status === "READY").length} 份可用于问答` : "先选择一个知识库"}
      </p>
      <CurrentSources onOpen={onOpenSource} />

      {documents.documents.length ? (
        <div className={styles.docList}>
          {documents.documents.map((document) => (
            <div className={styles.docRow} key={document.id}>
              <span className={styles.docBadge}>{formatLabel(document.format)}</span>
              <span className={styles.docText}>
                <strong title={document.original_name}>{document.original_name}</strong>
                <small>{formatBytes(document.byte_size)}</small>
              </span>
              <StatusBadge status={document.status} />
            </div>
          ))}
        </div>
      ) : (
        <div className={styles.docsEmpty}>
          <FileText size={20} strokeWidth={1.5} aria-hidden="true" />
          <p>还没有资料</p>
          <span>支持 TXT、Markdown 与可读取文本的 PDF，最大 8 MiB。</span>
        </div>
      )}

      {documents.hasMore && (
        <button className={styles.loadMore} onClick={() => void documents.loadMore()} disabled={documents.loadingMore}>
          加载更多资料
        </button>
      )}

      <div className={styles.privacy}>
        <CircleHelp size={16} aria-hidden="true" />
        <p>资料只对当前账户可见。索引显示“已就绪”后才会参与问答。</p>
      </div>

      {selected && (
        <Link className={styles.docsLink} href={`/knowledge-bases/${selected.id}`}>
          <FolderOpen size={16} aria-hidden="true" /> 打开知识库管理
        </Link>
      )}
    </div>
  );
}

export function ChatView() {
  const router = useRouter();
  const params = useParams<{ questionId?: string }>();
  const questionId = params?.questionId;
  const knowledge = useKnowledgeContext();
  const documents = useDocumentsContext();
  const questions = useQuestionsContext();
  const stream = useStreamControls();
  const { readyDocuments } = documents;
  const { clearDraft, setDraft } = useDraftActions();
  const loadAnswer = stream.load;
  const selectBase = knowledge.selectBase;
  const [viewing, setViewing] = useState<{ source: Source; documentName: string } | null>(null);
  const [sourceTrigger, setSourceTrigger] = useState<HTMLElement | null>(null);
  const [panel, setPanel] = useState<"history" | "docs" | null>(null);
  const loaded = useRef("");

  useEffect(() => {
    if (!questionId) {
      loaded.current = "";
      return;
    }
    if (loaded.current === questionId) return;
    loaded.current = questionId;
    void loadAnswer(questionId).then((detail) => {
      if (detail) selectBase(detail.knowledge_base_id);
    });
  }, [questionId, selectBase, loadAnswer]);

  function ask(question: string) {
    if (!knowledge.selectedBase) return;
    if (questionId) router.replace("/conversations");
    clearDraft();
    void stream.ask(question, knowledge.selectedBase);
  }

  function newChat() {
    stream.reset();
    clearDraft();
    router.push("/conversations");
  }

  const selected = knowledge.bases.find((base) => base.id === knowledge.selectedBase);

  function openSource(source: Source, documentName: string, trigger: HTMLButtonElement) {
    setSourceTrigger(trigger);
    setViewing({ source, documentName });
  }

  return (
    <div className={styles.page}>
      <header className="workspace-header">
        <div className={styles.chatTitle}>
          <p className={styles.eyebrow}>Conversations</p>
          <h1 data-display-heading>对话</h1>
          <p className={styles.chatMeta}>
            {selected ? selected.name : "选择一个知识库开始"} · {readyDocuments.length} 份资料可用于问答
          </p>
        </div>
        <div className={styles.chatActions} data-header-actions>
          {knowledge.bases.length > 1 && (
            <label className={styles.baseSelect} data-composite-field>
              <Layers size={16} aria-hidden="true" />
              <select
                name="knowledge-base"
                autoComplete="off"
                aria-label="切换知识库"
                value={knowledge.selectedBase}
                onChange={(event) => {
                  stream.reset();
                  clearDraft();
                  knowledge.selectBase(event.target.value);
                }}
              >
                {knowledge.bases.map((base) => <option key={base.id} value={base.id}>{base.name}</option>)}
              </select>
            </label>
          )}
          <Button variant="secondary" size="sm" className={styles.mobileOnly} onClick={() => setPanel("history")}>
            <PanelLeft size={16} aria-hidden="true" /> 历史记录
          </Button>
          <Button variant="secondary" size="sm" className={styles.mobileOnly} onClick={() => setPanel("docs")}>
            <PanelRight size={16} aria-hidden="true" /> 资料
          </Button>
          <Button variant="secondary" size="sm" onClick={newChat}>
            <Plus size={16} aria-hidden="true" /> 新对话
          </Button>
        </div>
      </header>

      {documents.notice && (
        <div className={styles.chatNotice} role="status">
          <span>{documents.notice}</span>
          <button onClick={documents.clearNotice}>关闭</button>
        </div>
      )}
      {stream.notice && (
        <div className={styles.chatNotice} role="alert">
          <span>{stream.notice}</span>
          <button onClick={stream.clearNotice}>关闭</button>
        </div>
      )}

      <div className={styles.layout}>
        <aside className={styles.railColumn}>
          <HistoryRail
            items={questions.history}
            loading={questions.loading}
            hasMore={questions.hasMore}
            activeId={questionId}
            onLoadMore={() => void questions.loadMore()}
            onNew={newChat}
          />
        </aside>

        <section className={styles.chatMain} aria-label="问答">
          <div className={styles.answerScroll}>
            <AnswerPanel
              onOpenSource={openSource}
              onEditQuestion={(question) => {
                setDraft(question);
                requestAnimationFrame(() => document.getElementById("desk-question")?.focus());
              }}
              onDeleted={(deletedId) => {
                loaded.current = "";
                if (questionId === deletedId) router.replace("/conversations");
              }}
            />
          </div>
          <Composer onAsk={ask} />
        </section>

        <aside className={styles.docsColumn}>
          <DocumentsPanel onOpenSource={openSource} />
        </aside>
      </div>

      <OnDemand open={panel !== null}>
        <MobilePanel panel={panel} onClose={() => setPanel(null)}>
          {panel === "history" ? (
            <HistoryRail
              items={questions.history}
              loading={questions.loading}
              hasMore={questions.hasMore}
              activeId={questionId}
              onLoadMore={() => void questions.loadMore()}
              onNew={() => { setPanel(null); newChat(); }}
              onNavigate={() => setPanel(null)}
            />
          ) : <DocumentsPanel onOpenSource={openSource} />}
        </MobilePanel>
      </OnDemand>

      <OnDemand open={viewing !== null}>
        <SourceDialog
          source={viewing?.source ?? null}
          documentName={viewing?.documentName ?? ""}
          open={viewing !== null}
          onOpenChange={(open) => { if (!open) setViewing(null); }}
          returnFocus={sourceTrigger}
        />
      </OnDemand>

    </div>
  );
}
