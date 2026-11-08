"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Page, type QuestionHistory } from "@/services/api";
import { messageOf } from "@/lib/format";

export function useQuestions(userId?: string) {
  const [history, setHistory] = useState<QuestionHistory[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const offsetRef = useRef(0);
  const loadingRef = useRef(false);
  const generation = useRef(0);

  const load = useCallback(async () => {
    if (!userId) return;
    await Promise.resolve();
    const gen = ++generation.current;
    setLoading(true);
    try {
      const page = await api<Page<QuestionHistory>>("questions?limit=50&offset=0");
      if (gen !== generation.current) return;
      setHistory(page.items);
      offsetRef.current = page.items.length;
      setHasMore(Boolean(page.has_more));
    } catch (reason) {
      if (gen === generation.current) setNotice(messageOf(reason));
    } finally {
      if (gen === generation.current) setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    queueMicrotask(() => { void load(); });
  }, [load]);

  async function loadMore() {
    if (loadingRef.current || !hasMore) return;
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
      setLoading(false);
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

  return { history, hasMore, loading, notice, load, loadMore, remove, clearNotice };
}
