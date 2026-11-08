"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useSession } from "@/hooks/use-session";
import { useKnowledgeBases } from "@/hooks/use-knowledge-bases";
import { useDocuments } from "@/hooks/use-documents";
import { useQuestions } from "@/hooks/use-questions";
import { useQuestionStream } from "@/hooks/use-question-stream";
import { actions, useWorkspace, useWorkspaceDispatch } from "@/components/store";
import { Button } from "@/components/ui/button";
import styles from "./workspace.module.css";

function useWorkspaceData() {
  const router = useRouter();
  const dispatch = useWorkspaceDispatch();
  const draft = useWorkspace((state) => state.draft);
  const session = useSession();
  const userId = session.user?.user_id;
  const knowledge = useKnowledgeBases(userId);
  const documents = useDocuments(knowledge.selectedBase, userId);
  const questions = useQuestions(userId);

  const settle = useCallback(() => {
    void documents.refresh(knowledge.selectedBase);
    void questions.load();
  }, [documents, knowledge.selectedBase, questions]);

  const stream = useQuestionStream(settle);
  const resetStream = stream.reset;

  // Account switch: never keep the previous account's answer or draft around.
  useEffect(() => {
    resetStream();
    dispatch(actions.clearDraft());
  }, [userId, resetStream, dispatch]);

  useEffect(() => {
    if (!session.loading && !session.error && !session.user) {
      router.replace("/login");
    }
  }, [router, session.error, session.loading, session.user]);

  useEffect(() => {
    const expired = () => toast.error("登录状态已失效，请重新登录。");
    window.addEventListener("knowflow-session-expired", expired);
    return () => window.removeEventListener("knowflow-session-expired", expired);
  }, []);

  const readyDocuments = useMemo(
    () => documents.documents.filter((document) => document.status === "READY" && document.active_index_version_id),
    [documents.documents],
  );

  const setDraft = useCallback((value: string) => dispatch(actions.setDraft(value)), [dispatch]);
  const clearDraft = useCallback(() => dispatch(actions.clearDraft()), [dispatch]);

  return {
    session,
    knowledge,
    documents,
    questions,
    stream,
    readyDocuments,
    draft,
    setDraft,
    clearDraft,
  };
}

export type WorkspaceValue = ReturnType<typeof useWorkspaceData>;

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function useWorkspaceDataContext() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("Workspace context is unavailable.");
  return value;
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const value = useWorkspaceData();
  const { session } = value;

  if (session.loading) {
    return <main className={styles.gate} role="status">正在检查登录状态…</main>;
  }

  if (session.error) {
    return (
      <main className={styles.gate}>
        <div className={styles.gateCard} role="alert">
          <p className={styles.gateEyebrow}>连接中断</p>
          <h1>暂时无法连接工作区</h1>
          <p className={styles.gateText}>{session.error}</p>
          <Button onClick={session.retry}>重试连接</Button>
        </div>
      </main>
    );
  }

  if (!session.user) {
    return <main className={styles.gate} role="status">正在前往登录…</main>;
  }

  if (!value.knowledge.ready || !value.questions.ready) {
    return <main className={styles.gate} role="status">正在准备你的工作区…</main>;
  }

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
