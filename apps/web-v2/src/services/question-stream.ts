import type { Source } from "./api";

function validSource(value: unknown): value is Source {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Source>;
  return typeof item.source_id === "string" && Boolean(item.source_id) && typeof item.document_id === "string" && Boolean(item.document_id) && typeof item.content_version_id === "string" && Boolean(item.content_version_id) && (item.quote === null || typeof item.quote === "string") && (item.locator === null || typeof item.locator === "object" && item.locator !== undefined && typeof item.locator.kind === "string");
}

export async function streamQuestion(response: Response, onDelta: (value: string) => void, onSources: (value: Source[], hasAnswer: boolean) => void) {
  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => null) as { code?: string; message?: string } | null;
    throw new Error(error?.message ?? `问答请求失败（${response.status}）`);
  }
  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffered = "";
  let sequence = 0;
  let completed = false;
  let started = false;
  let sourcesReceived = false;
  let requestId = response.headers.get("x-request-id");
  const consume = (frame: string) => {
    if (frame.length > 1024 * 1024) throw new Error("问答事件过大，请查看历史记录。");
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    let payload: { sequence: number; contract_version: string; request_id: string; event: string; delta?: string; has_answer?: boolean; sources?: Source[]; code?: string; message?: string };
    try { payload = JSON.parse(data.join("\n")) as typeof payload; }
    catch { throw new Error("问答事件数据异常，请查看历史记录。"); }
    if (!payload || !Number.isInteger(payload.sequence) || payload.sequence !== sequence + 1) throw new Error("问答事件顺序异常，请查看历史记录。");
    sequence = payload.sequence;
    if (typeof payload.request_id !== "string" || !payload.request_id || requestId !== null && payload.request_id !== requestId) throw new Error("问答请求标识异常，请查看历史记录。");
    requestId = payload.request_id;
    if (completed || payload.contract_version !== "0.2.0" || payload.event !== event
      || !["started", "delta", "sources", "completed", "error", "cancelled"].includes(event)
      || event === "started" && started
      || !started && event !== "started" && event !== "error"
      || event === "delta" && (sourcesReceived || typeof payload.delta !== "string" || !payload.delta)
      || event === "sources" && (sourcesReceived || !Array.isArray(payload.sources) || !payload.sources.every(validSource)
        || typeof payload.has_answer !== "boolean" || payload.sources.length > 5 || payload.has_answer !== (payload.sources.length > 0))
      || event === "completed" && !sourcesReceived) throw new Error("问答事件状态异常，请查看历史记录。");
    if (event === "started") started = true;
    if (event === "delta" && payload.delta) onDelta(payload.delta);
    if (event === "sources") { sourcesReceived = true; onSources(payload.sources!, payload.has_answer!); }
    if (event === "cancelled") throw new DOMException(payload.message ?? "问答未能完成", "AbortError");
    if (event === "error") throw new Error(payload.message ?? payload.code ?? "问答未能完成");
    if (event === "completed") completed = true;
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffered += decoder.decode(value, { stream: !done });
      const frames = buffered.split(/\r?\n\r?\n/);
      buffered = frames.pop() ?? "";
      for (const frame of frames) consume(frame);
      if (buffered.length > 1024 * 1024) throw new Error("问答事件过大，请查看历史记录。");
      if (done && buffered.trim()) consume(buffered);
      if (done) buffered = "";
      if (done || completed) break;
    }
    if (!completed) throw new Error("连接已中断，答案可能未完成。请查看历史记录，不会自动重发。");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
