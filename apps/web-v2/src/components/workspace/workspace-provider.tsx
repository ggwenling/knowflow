"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { useSession } from "@/hooks/use-session";
import { useKnowledgeBases } from "@/hooks/use-knowledge-bases";
import { useDocuments } from "@/hooks/use-documents";
import { useQuestions } from "@/hooks/use-questions";
import { useQuestionStream } from "@/hooks/use-question-stream";
import { actions, useWorkspaceDispatch } from "@/components/store";
import { Button } from "@/components/ui/button";
import styles from "./workspace.module.css";

const SessionContext = createContext<ReturnType<typeof useSession> | null>(null);
const KnowledgeContext = createContext<ReturnType<typeof useKnowledgeBases> | null>(null);
const DocumentsContext = createContext<ReturnType<typeof useDocuments> | null>(null);
const QuestionsContext = createContext<ReturnType<typeof useQuestions> | null>(null);
const StreamContext = createContext<ReturnType<typeof useQuestionStream> | null>(null);
const StreamControlsContext = createContext<ReturnType<typeof useQuestionStream>["controls"] | null>(null);

function required<T>(value: T | null): T {
  if (value === null) throw new Error("Workspace context is unavailable.");
  return value;
}
export function useSessionContext() { return required(useContext(SessionContext)); }
export function useKnowledgeContext() { return required(useContext(KnowledgeContext)); }
export function useDocumentsContext() { return required(useContext(DocumentsContext)); }
export function useQuestionsContext() { return required(useContext(QuestionsContext)); }
export function useStreamContext() { return required(useContext(StreamContext)); }
export function useStreamControls() { return required(useContext(StreamControlsContext)); }

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const dispatch = useWorkspaceDispatch();
  const session = useSession();
  const userId = session.user?.user_id;
  const [streamOwner, setStreamOwner] = useState<string | undefined>(undefined);
  const knowledge = useKnowledgeBases(userId);
  const params = useParams<{ baseId?: string }>();
  // A detail URL owns its document reads and mutations. Background list or
  // shared-selection updates must never redirect actions into a different base.
  const documentBaseId = params?.baseId ?? knowledge.selectedBase;
  const documents = useDocuments(documentBaseId, userId);
  const questions = useQuestions(userId);
  const refreshDocuments = documents.refresh;
  const refreshQuestions = questions.load;
  const settle = useCallback(() => {
    void refreshDocuments();
    void refreshQuestions();
  }, [refreshDocuments, refreshQuestions]);
  const stream = useQuestionStream(settle);
  const resetStream = stream.reset;

  useEffect(() => {
    resetStream();
    dispatch(actions.clearDraft());
    let active = true;
    queueMicrotask(() => { if (active) setStreamOwner(userId); });
    return () => { active = false; };
  }, [userId, resetStream, dispatch]);
  useEffect(() => {
    if (!session.loading && !session.error && !session.user) router.replace("/login");
  }, [router, session.error, session.loading, session.user]);
  useEffect(() => {
    const expired = () => toast.error("登录状态已失效，请重新登录。");
    window.addEventListener("knowflow-session-expired", expired);
    return () => window.removeEventListener("knowflow-session-expired", expired);
  }, []);

  if (session.loading) return <main className={styles.gate} role="status">正在检查登录状态…</main>;
  if (session.error) return (
    <main className={styles.gate}>
      <div className={styles.gateCard} role="alert">
        <p className={styles.gateEyebrow}>连接中断</p>
        <h1>暂时无法连接工作区</h1>
        <p className={styles.gateText}>{session.error}</p>
        <Button onClick={session.retry}>重试连接</Button>
      </div>
    </main>
  );
  if (!session.user) return <main className={styles.gate} role="status">正在前往登录…</main>;

  // Settle the account reset before mounting route effects (e.g. loading a deep-linked answer).
  if (streamOwner !== userId) return <main className={styles.gate} role="status">正在准备你的工作区…</main>;

  // Authentication/account reset gates the shell; remote lists never do.
  // Stable domain values keep draft edits and answer deltas out of unrelated consumers.
  return (
    <SessionContext.Provider value={session}>
      <KnowledgeContext.Provider value={knowledge}>
        <DocumentsContext.Provider value={documents}>
          <QuestionsContext.Provider value={questions}>
            <StreamControlsContext.Provider value={stream.controls}>
              <StreamContext.Provider value={stream}>{children}</StreamContext.Provider>
            </StreamControlsContext.Provider>
          </QuestionsContext.Provider>
        </DocumentsContext.Provider>
      </KnowledgeContext.Provider>
    </SessionContext.Provider>
  );
}
