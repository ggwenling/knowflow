import { reportPerformance } from "@/lib/performance";

export type User = { user_id: string; email: string };
export type KnowledgeBase = { id: string; name: string; status: string; updated_at?: string };
export type Document = { id: string; original_name: string; status: string; format: string; byte_size: number; active_index_version_id?: string; latest_task_id?: string; latest_task_status?: string; current_content_version_id?: string };
export type Source = { source_id: string; document_id: string; content_version_id: string; quote: string | null; locator: { kind: string; page: number | null; start: number | null; end: number | null; unit: string | null } | null };
export type QuestionHistory = { question_id: string; knowledge_base_id: string; question: string; status: string; finished_at: string | null };
export type QuestionDetail = QuestionHistory & { answer: string | null; has_answer: boolean | null; failure_code: string | null; sources: Source[] };
export type Task = { task_id: string; status: string; failure_code: string | null };
export type Page<T> = { items: T[]; has_more: boolean };
export type ApiError = Error & { code?: string; status?: number };

export { streamQuestion } from "./question-stream";

export async function apiFetch(path: string, init: RequestInit = {}) {
  const start = performance.now();
  reportPerformance("api_request", 1, "count");
  try {
    const response = await fetch("/api/v1/" + path, { ...init, credentials: "same-origin", cache: "no-store" });
    reportPerformance("api_headers_ms", performance.now() - start, "ms", response.ok ? "ok" : "failed");
    if (response.status === 401 && !path.startsWith("auth/") && path !== "me") window.dispatchEvent(new Event("knowflow-session-expired"));
    return response;
  } catch (reason) {
    reportPerformance("api_headers_ms", performance.now() - start, "ms", init.signal?.aborted ? "cancelled" : "failed");
    throw reason;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) headers.set("content-type", "application/json");
  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { code?: string; message?: string } | null;
    const error = new Error(body?.message ?? `请求失败（${response.status}）`) as ApiError;
    error.code = body?.code; error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function deleteKnowledgeBase(id: string, signal?: AbortSignal) {
  await api(`knowledge-bases/${encodeURIComponent(id)}`, { method: "DELETE", signal });
}
