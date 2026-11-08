"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, deleteKnowledgeBase, type KnowledgeBase, type Page } from "@/services/api";
import { messageOf } from "@/lib/format";

const contractVersion = "0.2.0";

export function useKnowledgeBases(userId?: string) {
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [selectedBase, setSelectedBase] = useState("");
  const [loading, setLoading] = useState(Boolean(userId));
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [readyFor, setReadyFor] = useState<string | null>(null);
  const selectedRef = useRef("");
  const ownerRef = useRef<string | undefined>(undefined);
  const generation = useRef(0);
  const workToken = useRef<symbol | null>(null);
  const listRequest = useRef<AbortController | null>(null);
  const ownerRequest = useRef<AbortController | null>(null);

  const selectBase = useCallback((id: string) => {
    selectedRef.current = id;
    setSelectedBase(id);
  }, []);

  const beginWork = useCallback(() => {
    const token = Symbol("knowledge-base-work");
    workToken.current = token;
    setWorking(true);
    return token;
  }, []);

  // Only the operation that currently owns the workspace may clear the busy flag.
  const endWork = useCallback((token: symbol) => {
    if (workToken.current !== token) return;
    workToken.current = null;
    setWorking(false);
  }, []);

  const resetFor = useCallback(() => {
    setBases([]);
    selectBase("");
    setError("");
    setReadyFor(null);
    workToken.current = null;
    setWorking(false);
    setLoading(false);
  }, [selectBase]);

  const load = useCallback(async () => {
    const owner = userId;
    const current = ++generation.current;
    listRequest.current?.abort();
    const request = new AbortController();
    listRequest.current = request;
    if (ownerRef.current !== owner) {
      // A different account owns the workspace now: drop every trace of the old one.
      ownerRef.current = owner;
      resetFor();
    }
    if (!owner) return;
    // Yield before touching state so the effect never commits a cascading render.
    await Promise.resolve();
    if (current !== generation.current) return;
    setLoading(true);
    setError("");
    try {
      const items: KnowledgeBase[] = [];
      for (let offset = 0; ; ) {
        if (current !== generation.current || request.signal.aborted) return;
        const page = await api<Page<KnowledgeBase>>(`knowledge-bases?limit=50&offset=${offset}`, { signal: request.signal });
        if (current !== generation.current || request.signal.aborted) return;
        items.push(...page.items);
        // Publish each page; unrelated routes never wait for the full collection.
        // OFFSET pages are not a snapshot: absence cannot invalidate an explicit
        // selection such as a newly created base verified through its detail URL.
        setBases([...items]);
        if (!selectedRef.current) selectBase(items[0]?.id ?? "");
        setReadyFor(owner);
        if (!page.has_more || !page.items.length) break;
        offset += page.items.length;
      }
    } catch (reason) {
      if (current === generation.current && !request.signal.aborted) {
        setError(messageOf(reason));
        // Settle the gate so the page can surface the failure instead of waiting forever.
        setReadyFor(owner);
      }
    } finally {
      if (current === generation.current) {
        setLoading(false);
      }
    }
  }, [userId, resetFor, selectBase]);

  useEffect(() => {
    // Invalidate in-flight work; load() clears the previous account's data off-render.
    generation.current += 1;
    const request = new AbortController();
    ownerRequest.current = request;
    queueMicrotask(() => { if (!request.signal.aborted) void load(); });
    return () => {
      generation.current += 1;
      request.abort();
      listRequest.current?.abort();
    };
  }, [load]);

  const create = useCallback(async (name: string): Promise<
    { status: "ok"; base: KnowledgeBase } | { status: "failed" } | { status: "stale" }
  > => {
    const gen = generation.current;
    const token = beginWork();
    setError("");
    try {
      const created = await api<KnowledgeBase>("knowledge-bases", {
        method: "POST",
        body: JSON.stringify({ contract_version: contractVersion, name }),
        signal: ownerRequest.current?.signal,
      });
      // Another account owns the workspace now: never report this as its own result.
      if (gen !== generation.current) return { status: "stale" };
      setBases((previous) => [created, ...previous.filter((item) => item.id !== created.id)]);
      selectBase(created.id);
      return { status: "ok", base: created };
    } catch (reason) {
      if (gen !== generation.current) return { status: "stale" };
      setError(messageOf(reason));
      return { status: "failed" };
    } finally {
      endWork(token);
    }
  }, [beginWork, endWork, selectBase]);

  const remove = useCallback(async (id: string): Promise<"ok" | "failed" | "stale"> => {
    const gen = generation.current;
    const token = beginWork();
    setError("");
    try {
      await deleteKnowledgeBase(id, ownerRequest.current?.signal);
      if (gen !== generation.current) return "stale";
      setBases((previous) => previous.filter((item) => item.id !== id));
      if (selectedRef.current === id) {
        const next = bases.find((item) => item.id !== id)?.id ?? "";
        selectBase(next);
      }
      // Deletion shifts every later OFFSET. Cancel/invalidate the old read and
      // rebuild from page one instead of filtering a now-incomplete snapshot.
      void load();
      return "ok";
    } catch (reason) {
      if (gen !== generation.current) return "stale";
      setError(messageOf(reason));
      return "failed";
    } finally {
      endWork(token);
    }
  }, [bases, beginWork, endWork, selectBase, load]);

  const clearError = useCallback(() => setError(""), []);

  const ready = Boolean(userId) && readyFor === userId;

  return useMemo(() => ({
    bases: ready ? bases : [], selectedBase: ready ? selectedBase : "", selectBase,
    loading: Boolean(userId) && (!ready || loading), working: ready && working, error: ready ? error : "", ready, load, create, remove, clearError,
  }), [bases, selectedBase, selectBase, userId, ready, loading, working, error, load, create, remove, clearError]);
}
