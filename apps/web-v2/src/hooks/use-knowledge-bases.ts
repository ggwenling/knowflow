"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
        const page = await api<Page<KnowledgeBase>>(`knowledge-bases?limit=50&offset=${offset}`);
        items.push(...page.items);
        if (!page.has_more || !page.items.length) break;
        offset += page.items.length;
      }
      if (current !== generation.current) return;
      setBases(items);
      const next = items.find((item) => item.id === selectedRef.current)?.id ?? items[0]?.id ?? "";
      selectBase(next);
      setReadyFor(owner);
    } catch (reason) {
      if (current === generation.current) {
        setError(messageOf(reason));
        // Settle the gate so the page can surface the failure instead of waiting forever.
        setReadyFor(owner);
      }
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [userId, resetFor, selectBase]);

  useEffect(() => {
    // Invalidate in-flight work; load() clears the previous account's data off-render.
    generation.current += 1;
    queueMicrotask(() => { void load(); });
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
      await deleteKnowledgeBase(id);
      if (gen !== generation.current) return "stale";
      setBases((previous) => previous.filter((item) => item.id !== id));
      if (selectedRef.current === id) {
        const next = bases.find((item) => item.id !== id)?.id ?? "";
        selectBase(next);
      }
      return "ok";
    } catch (reason) {
      if (gen !== generation.current) return "stale";
      setError(messageOf(reason));
      return "failed";
    } finally {
      endWork(token);
    }
  }, [bases, beginWork, endWork, selectBase]);

  const clearError = useCallback(() => setError(""), []);

  const ready = Boolean(userId) && readyFor === userId;

  return { bases, selectedBase, selectBase, loading, working, error, ready, load, create, remove, clearError };
}
