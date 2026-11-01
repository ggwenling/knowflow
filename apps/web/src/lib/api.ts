export type User = { user_id: string; email: string };
export type KnowledgeBase = { id: string; name: string; status: string };
export type Document = {
  id: string;
  original_name: string;
  status: string;
  format: string;
  byte_size: number;
  active_index_version_id?: string;
  current_content_version_id?: string;
};
export type Source = {
  source_id: string;
  document_id: string;
  content_version_id: string;
  quote: string | null;
  locator: { kind: string; page: number | null; start: number | null; end: number | null; unit: string | null } | null;
};
export type QuestionHistory = {
  question_id: string;
  knowledge_base_id: string;
  question: string;
  status: string;
  finished_at: string | null;
};
export type QuestionDetail = QuestionHistory & {
  answer: string | null;
  has_answer: boolean | null;
  failure_code: string | null;
  sources: Source[];
};
export type ApiError = Error & { code?: string; status?: number };

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(`/api/v1/${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { code?: string; message?: string } | null;
    const error = new Error(body?.message ?? `请求失败（${response.status}）`) as ApiError;
    error.code = body?.code;
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function streamQuestion(
  response: Response,
  onDelta: (value: string) => void,
  onSources: (value: Source[]) => void,
) {
  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => null) as { code?: string; message?: string } | null;
    throw new Error(error?.message ?? `问答请求失败（${response.status}）`);
  }

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffered = "";
  let sequence = 0;
  let completed = false;
  const consume = (frame: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n")) as {
      sequence: number;
      delta?: string;
      sources?: Source[];
      code?: string;
      message?: string;
    };
    if (!Number.isInteger(payload.sequence) || payload.sequence !== sequence + 1) {
      throw new Error("问答事件顺序异常，请查看历史记录。");
    }
    sequence = payload.sequence;
    if (event === "delta" && payload.delta) onDelta(payload.delta);
    if (event === "sources" && payload.sources) onSources(payload.sources);
    if (event === "error" || event === "cancelled") {
      throw new Error(payload.message ?? payload.code ?? "问答未能完成");
    }
    if (event === "completed") completed = true;
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffered += decoder.decode(value, { stream: !done });
      const frames = buffered.split(/\r?\n\r?\n/);
      buffered = frames.pop() ?? "";
      for (const frame of frames) consume(frame);
      if (done && buffered.trim()) consume(buffered);
      if (done) buffered = "";
      if (done) break;
    }
    if (!completed) throw new Error("连接已中断，答案可能未完成。请查看历史记录，不会自动重发。");
  } finally {
    reader.releaseLock();
  }
}
