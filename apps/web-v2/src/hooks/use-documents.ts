"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Document, type Page, type Task } from "@/services/api";
import { messageOf } from "@/lib/format";

const terminal = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const maxUploadBytes = 8 * 1024 * 1024;

export function useDocuments(baseId: string, ownerId?: string) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const generation = useRef(0);
  const baseRef = useRef(baseId);
  const ownerRef = useRef(ownerId);
  const offsetRef = useRef(0);
  const refreshSeq = useRef(0);
  const loadingMoreRef = useRef(false);
  const polling = useRef(new Set<string>());
  const workToken = useRef<symbol | null>(null);

  const clearNotice = useCallback(() => setNotice(""), []);

  // Only the newest operation may clear the shared busy flag, so a request left
  // over from another knowledge base can never re-enable controls mid-operation.
  const beginWork = useCallback(() => {
    const token = Symbol("documents-work");
    workToken.current = token;
    setWorking(true);
    return token;
  }, []);

  const endWork = useCallback((token: symbol) => {
    if (workToken.current !== token) return;
    workToken.current = null;
    setWorking(false);
  }, []);

  async function refresh(id = baseRef.current) {
    if (!id) {
      setDocuments([]);
      setHasMore(false);
      return [];
    }
    const gen = generation.current;
    const seq = ++refreshSeq.current;
    setRefreshing(true);
    try {
      const page = await api<Page<Document>>(`knowledge-bases/${id}/documents?limit=50&offset=0`);
      if (gen !== generation.current || seq !== refreshSeq.current || baseRef.current !== id) return [];
      setDocuments(page.items);
      offsetRef.current = page.items.length;
      setHasMore(Boolean(page.has_more));
      for (const document of page.items) void poll(document, gen, id);
      return page.items;
    } catch (reason) {
      if (gen === generation.current) setNotice(messageOf(reason));
      return [];
    } finally {
      if (seq === refreshSeq.current) setRefreshing(false);
    }
  }

  async function poll(document: Document, gen: number, ownerBase: string) {
    const taskId = document.latest_task_id;
    if (!taskId || terminal.has((document.latest_task_status ?? "").toUpperCase())) return;
    const key = `${gen}:${taskId}`;
    if (polling.current.has(key)) return;
    polling.current.add(key);
    let wait = 1500;
    try {
      for (;;) {
        if (gen !== generation.current || baseRef.current !== ownerBase) return;
        const [next, task] = await Promise.all([
          api<Document>(`documents/${document.id}`),
          api<Task>(`tasks/${taskId}`),
        ]);
        if (gen !== generation.current || baseRef.current !== ownerBase) return;
        setDocuments((previous) => previous.map((item) => (item.id === next.id ? next : item)));
        if (terminal.has(task.status.toUpperCase())) {
          await refresh(ownerBase);
          if (task.status.toUpperCase() !== "SUCCEEDED") {
            setNotice(task.failure_code ?? "索引未能完成；可以检查状态后重建。");
          }
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, wait));
        wait = Math.min(Math.round(wait * 1.35), 4000);
      }
    } catch (reason) {
      if (gen === generation.current && baseRef.current === ownerBase) setNotice(messageOf(reason));
    } finally {
      polling.current.delete(key);
    }
  }

  useEffect(() => {
    const ownerChanged = ownerRef.current !== ownerId;
    ownerRef.current = ownerId;
    baseRef.current = baseId;
    generation.current += 1;
    refreshSeq.current += 1;
    offsetRef.current = 0;
    loadingMoreRef.current = false;
    polling.current.clear();
    workToken.current = null;
    void (async () => {
      await Promise.resolve();
      setDocuments([]);
      setHasMore(false);
      setNotice("");
      setLoadingMore(false);
      setRefreshing(false);
      setWorking(false);
      // The still-selected base belongs to the previous account; never query it as the new one.
      if (baseId && !ownerChanged) await refresh(baseId);
    })();
    // The refresh function reads current refs; rerunning on identity change would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseId, ownerId]);

  async function loadMore() {
    if (loadingMoreRef.current || refreshing || !baseRef.current) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const id = baseRef.current;
    const gen = generation.current;
    const seq = refreshSeq.current;
    const offset = offsetRef.current;
    try {
      const page = await api<Page<Document>>(`knowledge-bases/${id}/documents?limit=50&offset=${offset}`);
      if (gen !== generation.current || seq !== refreshSeq.current || offsetRef.current !== offset) return;
      offsetRef.current += page.items.length;
      setDocuments((previous) => [
        ...previous,
        ...page.items.filter((item) => !previous.some((old) => old.id === item.id)),
      ]);
      setHasMore(Boolean(page.has_more));
      for (const document of page.items) void poll(document, gen, id);
    } catch (reason) {
      if (gen === generation.current) setNotice(messageOf(reason));
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }

  async function upload(file: File | undefined, updateTarget?: Document) {
    if (!file || !baseRef.current) return false;
    if (file.size > maxUploadBytes) {
      setNotice("文件大小不能超过 8 MiB。");
      return false;
    }
    const id = baseRef.current;
    const gen = generation.current;
    const token = beginWork();
    setNotice("");
    try {
      const form = new FormData();
      form.set("file", file);
      const path = updateTarget
        ? `documents/${updateTarget.id}/contents`
        : `knowledge-bases/${id}/documents`;
      const accepted = await api<{ document_id: string; task_id: string }>(path, { method: "POST", body: form });
      if (gen !== generation.current || baseRef.current !== id) return false;
      const optimistic: Document = {
        ...(updateTarget ?? {
          id: accepted.document_id,
          original_name: file.name,
          format: file.name.split(".").pop() ?? "",
          byte_size: file.size,
        }),
        status: "QUEUED",
        latest_task_id: accepted.task_id,
        latest_task_status: "QUEUED",
      };
      setDocuments((previous) => {
        if (updateTarget) return previous.map((item) => (item.id === optimistic.id ? optimistic : item));
        return [optimistic, ...previous];
      });
      await poll(optimistic, gen, id);
      return true;
    } catch (reason) {
      if (gen === generation.current) setNotice(messageOf(reason));
      return false;
    } finally {
      endWork(token);
    }
  }

  async function rebuild(document: Document) {
    const id = baseRef.current;
    if (!id) return false;
    const gen = generation.current;
    const token = beginWork();
    setNotice("");
    try {
      const accepted = await api<{ task_id: string }>(`documents/${document.id}/rebuilds`, {
        method: "POST",
        body: "{}",
      });
      // Indexing continues in the background; the row status and polling reflect progress.
      if (gen === generation.current && baseRef.current === id) {
        void poll({ ...document, latest_task_id: accepted.task_id, latest_task_status: "QUEUED" }, gen, id);
      }
      return true;
    } catch (reason) {
      if (gen === generation.current) setNotice(messageOf(reason));
      return false;
    } finally {
      endWork(token);
    }
  }

  async function remove(document: Document) {
    const id = baseRef.current;
    const gen = generation.current;
    const token = beginWork();
    setNotice("");
    try {
      await api(`documents/${document.id}`, { method: "DELETE" });
      if (gen === generation.current) {
        setDocuments((previous) => previous.filter((item) => item.id !== document.id));
        void refresh(id);
      }
      return true;
    } catch (reason) {
      if (gen === generation.current) setNotice(messageOf(reason));
      return false;
    } finally {
      endWork(token);
    }
  }

  return {
    documents,
    hasMore,
    refreshing,
    loadingMore,
    working,
    notice,
    clearNotice,
    refresh,
    loadMore,
    upload,
    rebuild,
    remove,
  };
}
