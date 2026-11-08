"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Page, type QuestionHistory } from "@/services/api";
import { messageOf } from "@/lib/format";

const empty: QuestionHistory[] = [];
export function useQuestions(userId?: string) {
  const [history, setHistory] = useState<QuestionHistory[]>(empty);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [readyFor, setReadyFor] = useState<string | null>(null);
  const scope = useRef<{ owner: string; controller: AbortController; generation: number; offset: number; pages: number; more: boolean; loading: boolean; paginating: boolean } | null>(null);

  const load = useCallback(async () => {
    const current = scope.current;
    if (!current || current.controller.signal.aborted) return;
    const gen = ++current.generation;
    current.loading = true;
    setLoading(true);
    setNotice("");
    try {
      let offset = 0;
      let more = false;
      const items: QuestionHistory[] = [];
      for (let i = 0; i < current.pages; i++) {
        if (current !== scope.current || gen !== current.generation) return;
        const page = await api<Page<QuestionHistory>>(`questions?limit=50&offset=${offset}`, { signal: current.controller.signal });
        if (current !== scope.current || gen !== current.generation) return;
        items.push(...page.items);
        offset += page.items.length;
        more = Boolean(page.has_more && page.items.length);
        if (!more) break;
      }
      current.offset = offset;
      current.more = more;
      setHistory(items);
      setHasMore(more);
      setReadyFor(current.owner);
    } catch (reason) {
      if (current === scope.current && gen === current.generation && !current.controller.signal.aborted) {
        setNotice(`问答历史加载失败：${messageOf(reason)}`);
        setReadyFor(current.owner);
      }
    } finally {
      if (current === scope.current && gen === current.generation) { current.loading = false; setLoading(current.paginating); }
    }
  }, []);

  useEffect(() => {
    const current = { owner: userId ?? "", controller: new AbortController(), generation: 0, offset: 0, pages: 1, more: false, loading: false, paginating: false };
    scope.current = current;
    queueMicrotask(() => {
      if (current.controller.signal.aborted) return;
      setHistory(empty); setHasMore(false); setNotice(""); setReadyFor(null); setLoading(false);
      if (current.owner) void load();
    });
    return () => { current.controller.abort(); current.generation++; if (scope.current === current) scope.current = null; };
  }, [userId, load]);

  const loadMore = useCallback(async () => {
    const current = scope.current;
    if (!current || current.loading || current.paginating || !current.more) return;
    current.paginating = true;
    setLoading(true);
    const gen = current.generation;
    const offset = current.offset;
    try {
      const page = await api<Page<QuestionHistory>>(`questions?limit=50&offset=${offset}`, { signal: current.controller.signal });
      if (current !== scope.current || gen !== current.generation || current.offset !== offset) return;
      current.offset += page.items.length;
      current.pages++;
      current.more = Boolean(page.has_more && page.items.length);
      setHistory((previous) => {
        const ids = new Set(previous.map((item) => item.question_id));
        return [...previous, ...page.items.filter((item) => !ids.has(item.question_id))];
      });
      setHasMore(current.more);
    } catch (reason) {
      if (current === scope.current && !current.controller.signal.aborted) setNotice(`加载更多问答失败：${messageOf(reason)}`);
    } finally {
      current.paginating = false;
      if (current === scope.current) setLoading(current.loading);
    }
  }, []);

  const clearNotice = useCallback(() => setNotice(""), []);
  const ready = Boolean(userId) && readyFor === userId;
  return useMemo(() => ({ history: ready ? history : empty, hasMore: ready && hasMore, loading: Boolean(userId) && (!ready || loading), notice: ready ? notice : "", ready, load, loadMore, clearNotice }), [history, hasMore, loading, notice, ready, userId, load, loadMore, clearNotice]);
}
