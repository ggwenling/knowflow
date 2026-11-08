"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, apiFetch, streamQuestion, type QuestionDetail, type Source } from "@/services/api";
import { messageOf } from "@/lib/format";
import { preloadMarkdown } from "@/components/chat/load-markdown";
import { reportPerformance } from "@/lib/performance";

export function useQuestionStream(onSettled: () => void) {
  const [answer, setAnswer] = useState<QuestionDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const controller = useRef<AbortController | null>(null);
  const view = useRef(0);
  const buffer = useRef("");
  const flushTimer = useRef<number | null>(null);
  const settled = useRef(onSettled);
  const answerId = useRef<string | null>(null);

  useEffect(() => {
    settled.current = onSettled;
  }, [onSettled]);

  useEffect(() => {
    answerId.current = answer?.question_id || null;
  }, [answer?.question_id]);

  const flush = useCallback(() => {
    if (flushTimer.current !== null) {
      window.clearTimeout(flushTimer.current);
      flushTimer.current = null;
    }
    const pending = buffer.current;
    buffer.current = "";
    if (!pending) return;
    setAnswer((old) => (old ? { ...old, answer: (old.answer ?? "") + pending } : old));
  }, []);

  // Abort the running stream and release everything that keeps the composer busy.
  const stop = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    if (flushTimer.current !== null) {
      window.clearTimeout(flushTimer.current);
      flushTimer.current = null;
    }
    buffer.current = "";
    setBusy(false);
  }, []);

  useEffect(() => () => {
    view.current++;
    controller.current?.abort();
    if (flushTimer.current !== null) window.clearTimeout(flushTimer.current);
  }, []);

  const ask = useCallback(async (question: string, knowledgeBaseId: string) => {
    const text = question.trim();
    if (!text || !knowledgeBaseId) return false;
    const viewId = ++view.current;
    const startedAt = performance.now();
    let firstDelta = true;
    const isCurrent = () => view.current === viewId;
    stop();
    const abort = new AbortController();
    controller.current = abort;
    setNotice("");
    setBusy(true);
    setAnswer({
      question_id: "",
      knowledge_base_id: knowledgeBaseId,
      question: text,
      status: "PROCESSING",
      finished_at: null,
      answer: "",
      has_answer: null,
      failure_code: null,
      sources: [],
    });

    try {
      const response = await apiFetch(`knowledge-bases/${knowledgeBaseId}/questions/stream`, {
        method: "POST",
        signal: abort.signal,
        headers: { "content-type": "application/json", "idempotency-key": crypto.randomUUID() },
        body: JSON.stringify({ question: text }),
      });
      if (!isCurrent()) return false;
      if (response.ok) preloadMarkdown();
      await streamQuestion(
        response,
        (delta) => {
          if (!isCurrent()) return;
          if (firstDelta) { reportPerformance("question_first_delta_ms", performance.now() - startedAt); firstDelta = false; }
          buffer.current += delta;
          if (flushTimer.current === null) {
            flushTimer.current = window.setTimeout(() => {
              flushTimer.current = null;
              flush();
            }, 50);
          }
        },
        (sources: Source[], hasAnswer: boolean) => {
          if (!isCurrent()) return;
          flush();
          setAnswer((old) => (old ? { ...old, sources, has_answer: hasAnswer } : old));
        },
      );
      if (!isCurrent()) return false;
      flush();
      setAnswer((old) => (old ? { ...old, status: "SUCCEEDED", finished_at: new Date().toISOString() } : old));
      reportPerformance("question_duration_ms", performance.now() - startedAt, "ms", "ok");
      settled.current();
      return true;
    } catch (reason) {
      if (!isCurrent()) return false;
      flush();
      const cancelled = abort.signal.aborted || (reason instanceof DOMException && reason.name === "AbortError");
      setAnswer((old) => (old ? {
        ...old,
        status: cancelled ? "CANCELLED" : "FAILED",
        failure_code: cancelled ? "用户停止生成" : messageOf(reason),
        has_answer: null,
        sources: [],
      } : old));
      if (!cancelled) setNotice(messageOf(reason));
      reportPerformance("question_duration_ms", performance.now() - startedAt, "ms", cancelled ? "cancelled" : "failed");
      settled.current();
      return false;
    } finally {
      if (view.current === viewId) {
        controller.current = null;
        setBusy(false);
      }
    }
  }, [flush, stop]);

  const cancel = useCallback(() => {
    controller.current?.abort();
    setNotice("正在停止请求。若生成已经开始，请在历史记录里确认状态，不会自动重发。");
  }, []);

  const load = useCallback(async (questionId: string) => {
    const viewId = ++view.current;
    // Switching to a stored question ends any in-flight generation and clears busy.
    stop();
    const abort = new AbortController();
    controller.current = abort;
    setAnswer(null);
    setNotice("");
    preloadMarkdown();
    try {
      const detail = await api<QuestionDetail>(`questions/${encodeURIComponent(questionId)}`, { signal: abort.signal });
      if (view.current !== viewId) return null;
      setAnswer(detail);
      return detail;
    } catch (reason) {
      if (view.current === viewId) {
        setAnswer(null);
        setNotice(messageOf(reason));
      }
      return null;
    }
  }, [stop]);

  const reset = useCallback(() => {
    view.current += 1;
    stop();
    setAnswer(null);
    setNotice("");
  }, [stop]);

  const remove = useCallback(async (questionId: string) => {
    const viewId = view.current;
    try {
      await api(`questions/${encodeURIComponent(questionId)}`, { method: "DELETE" });
      if (view.current !== viewId) return false;
      if (answerId.current === questionId) stop();
      setAnswer((old) => (old?.question_id === questionId ? null : old));
      settled.current();
      return true;
    } catch (reason) {
      if (view.current === viewId) setNotice(messageOf(reason));
      return false;
    }
  }, [stop]);

  const clearNotice = useCallback(() => setNotice(""), []);

  const controls = useMemo(() => ({ busy, notice, ask, cancel, load, reset, remove, clearNotice }), [busy, notice, ask, cancel, load, reset, remove, clearNotice]);
  return useMemo(() => ({ answer, ...controls, controls }), [answer, controls]);
}
