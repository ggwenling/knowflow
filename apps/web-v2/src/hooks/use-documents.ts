"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Document, type Page, type Task } from "@/services/api";
import { messageOf } from "@/lib/format";
import { uploadError } from "@/lib/upload-rules";
import { RequestScope, abortableDelay, waitUntilVisible } from "@/lib/request-scope";
import { reportPerformance } from "@/lib/performance";

const terminal = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const emptyDocuments: Document[] = [];
type Outcome = "ok" | "failed" | "stale";
type State = { identity: string; documents: Document[]; hasMore: boolean; refreshing: boolean; loadingMore: boolean; working: boolean; notice: string };
type Scope = {
  identity: string; base: string; requests: RequestScope; offset: number; pages: number; sequence: number;
  refreshing: boolean; morePending: boolean; work: symbol | null; refreshTimer: ReturnType<typeof setTimeout> | null;
  polls: Map<string, { documentId: string; controller: AbortController }>; finished: Set<string>; indexStarts: Map<string, number>;
};
const initial: State = { identity: "", documents: emptyDocuments, hasMore: false, refreshing: false, loadingMore: false, working: false, notice: "" };

function reconcile(previous: Document[], next: Document[]) {
  const old = new Map(previous.map((item) => [item.id, item]));
  const result = next.map((item) => {
    const before = old.get(item.id);
    return before && Object.keys({ ...before, ...item }).every((key) => before[key as keyof Document] === item[key as keyof Document]) ? before : item;
  });
  return result.length === previous.length && result.every((item, i) => item === previous[i]) ? previous : result;
}

export function useDocuments(baseId: string, ownerId?: string) {
  const identity = ownerId && baseId ? `${ownerId}:${baseId}` : "";
  const [state, setState] = useState<State>(initial);
  const active = useRef<Scope | null>(null);
  const current = useCallback((scope: Scope) => active.current === scope && !scope.requests.signal.aborted, []);
  const patch = useCallback((scope: Scope, update: Partial<State> | ((old: State) => Partial<State>)) => {
    if (!current(scope)) return;
    setState((old) => {
      if (old.identity !== scope.identity) return old;
      const changes = typeof update === "function" ? update(old) : update;
      if ((Object.keys(changes) as Array<keyof State>).every((key) => Object.is(old[key], changes[key]))) return old;
      return { ...old, ...changes };
    });
  }, [current]);

  const refresh = useCallback(async (id?: string): Promise<Document[]> => {
    const scope = active.current;
    if (!scope || !current(scope) || id && id !== scope.base) return [];
    const sequence = ++scope.sequence;
    scope.refreshing = true;
    patch(scope, { refreshing: true });
    try {
      const items: Document[] = [];
      let offset = 0;
      let more = false;
      // Revalidate the loaded range, not just page one. Preserve the user's pagination.
      for (let pageNumber = 0; pageNumber < scope.pages; pageNumber++) {
        if (!current(scope) || sequence !== scope.sequence) return [];
        const page = await scope.requests.run(() => api<Page<Document>>(`knowledge-bases/${encodeURIComponent(scope.base)}/documents?limit=50&offset=${offset}`, { signal: scope.requests.signal }));
        if (!current(scope) || sequence !== scope.sequence) return [];
        items.push(...page.items);
        offset += page.items.length;
        more = Boolean(page.has_more && page.items.length);
        if (!more) break;
      }
      scope.offset = offset;
      patch(scope, (old) => ({ documents: reconcile(old.documents, items), hasMore: more }));
      for (const document of items) startPoll(scope, document);
      return items;
    } catch (reason) {
      if (sequence === scope.sequence && !scope.requests.signal.aborted) patch(scope, { notice: messageOf(reason) });
      return [];
    } finally {
      if (current(scope) && sequence === scope.sequence) { scope.refreshing = false; patch(scope, { refreshing: false }); }
    }
  // Polling only closes over the stable scope helpers and refresh itself.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, patch]);

  function startPoll(scope: Scope, document: Document): void {
    const taskId = document.latest_task_id;
    if (!taskId || terminal.has((document.latest_task_status ?? "").toUpperCase()) || scope.finished.has(taskId) || scope.polls.has(taskId) || !current(scope)) return;
    const controller = new AbortController();
    const signal = AbortSignal.any([scope.requests.signal, controller.signal]);
    scope.polls.set(taskId, { documentId: document.id, controller });
    void (async () => {
      let wait = 1500;
      let failures = 0;
      try {
        while (!signal.aborted && current(scope)) {
          await waitUntilVisible(signal);
          try {
            const results: [Document, Task] = await Promise.all([
              scope.requests.run<Document>(async (): Promise<Document> => { await waitUntilVisible(signal); return api<Document>(`documents/${encodeURIComponent(document.id)}`, { signal }); }, signal),
              scope.requests.run<Task>(async (): Promise<Task> => { await waitUntilVisible(signal); return api<Task>(`tasks/${encodeURIComponent(taskId)}`, { signal }); }, signal),
            ]);
            const next: Document = results[0];
            const task: Task = results[1];
            if (signal.aborted || !current(scope)) return;
            failures = 0;
            patch(scope, (old) => ({ documents: reconcile(old.documents, old.documents.map((item) => item.id === next.id ? next : item)) }));
            if (next.latest_task_id && next.latest_task_id !== taskId) { startPoll(scope, next); return; }
            if (terminal.has(task.status.toUpperCase())) {
              scope.finished.add(taskId);
              const acceptedAt = scope.indexStarts.get(taskId);
              if (acceptedAt !== undefined) { reportPerformance("index_wait_ms", performance.now() - acceptedAt, "ms", task.status.toUpperCase() === "SUCCEEDED" ? "ok" : "failed"); scope.indexStarts.delete(taskId); }
              if (task.status.toUpperCase() !== "SUCCEEDED") patch(scope, { notice: `索引未能完成：${task.failure_code ?? "请检查资料后重建。"}` });
              // Many tasks finishing together trigger one revalidation of the loaded range.
              if (scope.refreshTimer === null) scope.refreshTimer = setTimeout(() => {
                scope.refreshTimer = null;
                if (current(scope)) void refresh(scope.base);
              }, 100);
              return;
            }
          } catch (reason) {
            if (signal.aborted) return;
            failures++;
            if (failures >= 3) { patch(scope, { notice: `状态同步失败：${messageOf(reason)} 请刷新后重试。` }); return; }
          }
          await abortableDelay(Math.round(wait * (.9 + Math.random() * .2)), signal);
          wait = Math.min(Math.round(wait * 1.35), 4000);
        }
      } catch (reason) { if (!signal.aborted) patch(scope, { notice: messageOf(reason) }); }
      finally { scope.polls.delete(taskId); }
    })();
  }

  useEffect(() => {
    const scope: Scope = { identity, base: baseId, requests: new RequestScope(4), offset: 0, pages: 1, sequence: 0, refreshing: false, morePending: false, work: null, refreshTimer: null, polls: new Map(), finished: new Set(), indexStarts: new Map() };
    active.current = scope;
    queueMicrotask(() => {
      if (!current(scope)) return;
      setState({ ...initial, identity });
      if (identity) void refresh(baseId);
    });
    return () => {
      scope.requests.abort();
      if (scope.refreshTimer !== null) clearTimeout(scope.refreshTimer);
      scope.polls.clear();
      if (active.current === scope) active.current = null;
    };
  }, [identity, baseId, current, refresh]);

  const loadMore = useCallback(async () => {
    const scope = active.current;
    if (!scope || !scope.identity || !current(scope) || scope.morePending || scope.refreshing) return;
    scope.morePending = true;
    const sequence = scope.sequence;
    const offset = scope.offset;
    patch(scope, { loadingMore: true });
    try {
      const page = await scope.requests.run(() => api<Page<Document>>(`knowledge-bases/${encodeURIComponent(scope.base)}/documents?limit=50&offset=${offset}`, { signal: scope.requests.signal }));
      if (!current(scope) || sequence !== scope.sequence) return;
      scope.offset += page.items.length;
      scope.pages++;
      patch(scope, (old) => {
        const ids = new Set(old.documents.map((item) => item.id));
        return { documents: [...old.documents, ...page.items.filter((item) => !ids.has(item.id))], hasMore: Boolean(page.has_more && page.items.length) };
      });
      for (const document of page.items) startPoll(scope, document);
    } catch (reason) { if (!scope.requests.signal.aborted) patch(scope, { notice: messageOf(reason) }); }
    finally { scope.morePending = false; patch(scope, { loadingMore: false }); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, patch]);

  const beginWork = useCallback((scope: Scope) => {
    if (!current(scope) || !scope.identity || scope.work) return null;
    const token = Symbol("documents-work");
    scope.work = token;
    patch(scope, { working: true, notice: "" });
    return token;
  }, [current, patch]);
  const endWork = useCallback((scope: Scope, token: symbol) => {
    if (scope.work !== token) return;
    scope.work = null;
    patch(scope, { working: false });
  }, [patch]);

  const upload = useCallback(async (file: File | undefined, target?: Document): Promise<"accepted" | "failed" | "stale"> => {
    const scope = active.current;
    if (!file || !scope || !scope.identity) return "failed";
    const error = uploadError(file);
    if (error) { patch(scope, { notice: error }); return "failed"; }
    const token = beginWork(scope);
    if (!token) return "failed";
    const startedAt = performance.now();
    try {
      const form = new FormData();
      form.set("file", file);
      const path = target ? `documents/${encodeURIComponent(target.id)}/contents` : `knowledge-bases/${encodeURIComponent(scope.base)}/documents`;
      const accepted = await api<{ document_id: string; task_id: string }>(path, { method: "POST", body: form, signal: scope.requests.signal });
      if (!current(scope)) return "stale";
      reportPerformance("upload_accept_ms", performance.now() - startedAt, "ms", "ok");
      scope.indexStarts.set(accepted.task_id, performance.now());
      const optimistic: Document = { ...(target ?? { id: accepted.document_id, original_name: file.name, format: file.name.split(".").pop() ?? "", byte_size: file.size }), status: "QUEUED", latest_task_id: accepted.task_id, latest_task_status: "QUEUED" };
      if (target?.latest_task_id) scope.polls.get(target.latest_task_id)?.controller.abort();
      patch(scope, (old) => ({ documents: target ? old.documents.map((item) => item.id === target.id ? optimistic : item) : [optimistic, ...old.documents] }));
      startPoll(scope, optimistic);
      return "accepted";
    } catch (reason) {
      if (!current(scope)) return "stale";
      patch(scope, { notice: messageOf(reason) });
      return "failed";
    } finally { endWork(scope, token); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [beginWork, current, endWork, patch]);

  const rebuild = useCallback(async (document: Document): Promise<Outcome> => {
    const scope = active.current;
    if (!scope) return "failed";
    const token = beginWork(scope);
    if (!token) return "failed";
    try {
      const accepted = await api<{ task_id: string }>(`documents/${encodeURIComponent(document.id)}/rebuilds`, { method: "POST", body: "{}", signal: scope.requests.signal });
      if (!current(scope)) return "stale";
      if (document.latest_task_id) scope.polls.get(document.latest_task_id)?.controller.abort();
      const next = { ...document, latest_task_id: accepted.task_id, latest_task_status: "QUEUED" };
      patch(scope, (old) => ({ documents: old.documents.map((item) => item.id === document.id ? next : item) }));
      startPoll(scope, next);
      return "ok";
    } catch (reason) {
      if (!current(scope)) return "stale";
      patch(scope, { notice: messageOf(reason) });
      return "failed";
    } finally { endWork(scope, token); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [beginWork, current, endWork, patch]);

  const remove = useCallback(async (document: Document): Promise<Outcome> => {
    const scope = active.current;
    if (!scope) return "failed";
    const token = beginWork(scope);
    if (!token) return "failed";
    try {
      await api(`documents/${encodeURIComponent(document.id)}`, { method: "DELETE", signal: scope.requests.signal });
      if (!current(scope)) return "stale";
      for (const poll of scope.polls.values()) if (poll.documentId === document.id) poll.controller.abort();
      patch(scope, (old) => ({ documents: old.documents.filter((item) => item.id !== document.id) }));
      void refresh(scope.base);
      return "ok";
    } catch (reason) {
      if (!current(scope)) return "stale";
      patch(scope, { notice: messageOf(reason) });
      return "failed";
    } finally { endWork(scope, token); }
  }, [beginWork, current, endWork, patch, refresh]);

  const clearNotice = useCallback(() => { const scope = active.current; if (scope) patch(scope, { notice: "" }); }, [patch]);
  const visible = state.identity === identity ? state : initial;
  const readyDocuments = useMemo(() => visible.documents.filter((document) => document.status === "READY" && document.active_index_version_id), [visible.documents]);
  return useMemo(() => ({ ...visible, readyDocuments, clearNotice, refresh, loadMore, upload, rebuild, remove }), [visible, readyDocuments, clearNotice, refresh, loadMore, upload, rebuild, remove]);
}
