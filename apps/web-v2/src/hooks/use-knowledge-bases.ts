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
  const selectedRef = useRef("");
  const generation = useRef(0);

  const selectBase = useCallback((id: string) => {
    selectedRef.current = id;
    setSelectedBase(id);
  }, []);

  const load = useCallback(async () => {
    if (!userId) return;
    // Yield before touching state so the effect never commits a cascading render.
    await Promise.resolve();
    const current = ++generation.current;
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
    } catch (reason) {
      if (current === generation.current) setError(messageOf(reason));
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [userId, selectBase]);

  useEffect(() => {
    queueMicrotask(() => { void load(); });
  }, [load]);

  const create = useCallback(async (name: string) => {
    setWorking(true);
    setError("");
    try {
      const created = await api<KnowledgeBase>("knowledge-bases", {
        method: "POST",
        body: JSON.stringify({ contract_version: contractVersion, name }),
      });
      setBases((previous) => [created, ...previous.filter((item) => item.id !== created.id)]);
      selectBase(created.id);
      return created;
    } catch (reason) {
      setError(messageOf(reason));
      return null;
    } finally {
      setWorking(false);
    }
  }, [selectBase]);

  const remove = useCallback(async (id: string) => {
    setWorking(true);
    setError("");
    try {
      await deleteKnowledgeBase(id);
      setBases((previous) => previous.filter((item) => item.id !== id));
      if (selectedRef.current === id) {
        const next = bases.find((item) => item.id !== id)?.id ?? "";
        selectBase(next);
      }
      return true;
    } catch (reason) {
      setError(messageOf(reason));
      return false;
    } finally {
      setWorking(false);
    }
  }, [bases, selectBase]);

  const clearError = useCallback(() => setError(""), []);

  return { bases, selectedBase, selectBase, loading, working, error, load, create, remove, clearError };
}
