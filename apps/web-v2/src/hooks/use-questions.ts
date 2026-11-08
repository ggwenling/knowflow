"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Page, type QuestionHistory } from "@/services/api";
import { messageOf } from "@/lib/format";

export function useQuestions(userId?: string) {
  const [history, setHistory] = useState<QuestionHistory[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [readyFor, setReadyFor] = useState<string | null>(null);
  const offsetRef = useRef(0);
  const ownerRef = useRef<string | undefined>(undefined);
  const loadingRef = useRef(false);
  const generation = useRef(0);

  const resetFor = useCallback(() => {
    setHistory([]);
    setHasMore(false);
    setNotice("");
    setReadyFor(null);
    setLoading(false);
    offsetRef.current = 0;
    loadingRef.current = false;
  }, []);

  const load = useCallback(async () => {
    const owner = userId;
    const gen = ++generation.current;
    if (ownerRef.current !== owner) {
      // A different account owns the workspace now: drop the old history and cursor.
      ownerRef.current = owner;
      resetFor();
    }
    if (!owner) return;
    await Promise.resolve();
    if (gen !== generation.current) return;
    setLoading(true);
    try {
      const page = await api<Page<QuestionHistory>>("questions?limit=50&offset=0");
      if (gen !== generation.current) return;
      setHistory(page.items);
      offsetRef.current = page.items.length;
      setHasMore(Boolean(page.has_more));
      setReadyFor(owner);
    } catch (reason) {
      if (gen === generation.current) {
        setNotice(messageOf(reason));
        // Settle the gate so the page can surface the failure instead of waiting forever.
        setReadyFor(owner);
      }
    } finally {
      if (gen === generation.current) setLoading(false);
    }
  }, [userId, resetFor]);

  useEffect(() => {
    // Invalidate in-flight work; load() clears the previous account's history off-render.
    generation.current += 1;
    queueMicrotask(() => { void load(); });
  }, [load]);

  async function loadMore() {
    if (!userId || loadingRef.current || !hasMore) return;
    loadingRef.current = true;
    setLoading(true);
    const gen = generation.current;
    const offset = offsetRef.current;
    try {
      const page = await api<Page<QuestionHistory>>(`questions?limit=50&offset=${offset}`);
      if (gen !== generation.current || offsetRef.current !== offset) return;
      offsetRef.current += page.items.length;
      setHistory((previous) => [
        ...previous,
        ...page.items.filter((item) => !previous.some((old) => old.question_id === item.question_id)),
      ]);
      setHasMore(Boolean(page.has_more));
    } catch (reason) {
      if (gen === generation.current) setNotice(messageOf(reason));
    } finally {
      loadingRef.current = false;
      if (gen === generation.current) setLoading(false);
    }
  }

  const remove = useCallback(async (questionId: string) => {
    try {
      await api(`questions/${questionId}`, { method: "DELETE" });
      setHistory((previous) => previous.filter((item) => item.question_id !== questionId));
      return true;
    } catch (reason) {
      setNotice(messageOf(reason));
      return false;
    }
  }, []);

  const clearNotice = useCallback(() => setNotice(""), []);

  const ready = Boolean(userId) && readyFor === userId;

  return { history, hasMore, loading, notice, ready, load, loadMore, remove, clearNotice };
}
