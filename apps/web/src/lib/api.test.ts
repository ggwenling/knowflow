import { describe, expect, it, vi } from "vitest";
import { streamQuestion } from "@/lib/api";

function responseFromChunks(chunks: Uint8Array[]) {
  return new Response(new ReadableStream({
    start(controller) { for (const chunk of chunks) controller.enqueue(chunk); controller.close(); },
  }), { headers: { "content-type": "text/event-stream" } });
}

describe("streamQuestion", () => {
  it.each(["mixed_request", "after_completed", "missing_sources", "delta_before_started", "delta_after_sources", "duplicate_started", "wrong_event", "wrong_header", "wrong_version"])("rejects invalid lifecycle: %s", async (mode) => {
    const events = ["started", "delta", "sources", "completed"].map((event, index) => ({
      event, sequence: index + 1, request_id: "r-1", delta: "正文", sources: [], has_answer: false,
    }));
    if (mode === "mixed_request") events[1].request_id = "r-2";
    if (mode === "after_completed") events.push({ ...events[1], sequence: 5 });
    if (mode === "missing_sources") events.splice(2, 1);
    if (mode === "delta_before_started") events[0].event = "delta";
    if (mode === "delta_after_sources") [events[1], events[2]] = [events[2], events[1]];
    if (mode === "duplicate_started") events[1].event = "started";
    const wire = events.map((item, index) => `event: ${item.event}\ndata: ${JSON.stringify({ ...item, contract_version: mode === "wrong_version" ? "old" : "0.2.0", sequence: index + 1, ...(mode === "wrong_event" ? { event: "other" } : {}) })}\n\n`).join("");
    const response = responseFromChunks([new TextEncoder().encode(wire)]);
    response.headers.set("x-request-id", mode === "wrong_header" ? "other" : "r-1");
    await expect(streamQuestion(response, vi.fn(), vi.fn())).rejects.toThrow();
  });

  it("decodes split UTF-8 frames, keeps source events and waits for completed", async () => {
    const body = [
      { sequence: 1, request_id: "r-1" },
      { sequence: 2, delta: "引用中文" },
      { sequence: 3, has_answer: true, sources: [{ source_id: "s-1" }] },
      { sequence: 4 },
    ];
    const wire = body.map((item, index) => {
      const event = ["started", "delta", "sources", "completed"][index];
      return `event: ${event}\ndata: ${JSON.stringify({ ...item, event, request_id: "r-1", contract_version: "0.2.0" })}\n\n`;
    }).join("");
    const bytes = new TextEncoder().encode(wire);
    const split = bytes.findIndex((value) => value >= 0xe4 && value <= 0xe9) + 1;
    const chunks = [bytes.slice(0, split), bytes.slice(split, -7), bytes.slice(-7)];
    const deltas: string[] = [];
    const sources: unknown[] = [];

    await streamQuestion(responseFromChunks(chunks), (value) => deltas.push(value), (value) => sources.push(...value));

    expect(deltas).toEqual(["引用中文"]);
    expect(sources).toHaveLength(1);
  });

  it("reports an interrupted stream and does not treat it as success", async () => {
    const wire = `event: started\ndata: {"sequence":1,"request_id":"r-1","event":"started","contract_version":"0.2.0"}\n\n`;
    await expect(streamQuestion(responseFromChunks([new TextEncoder().encode(wire)]), vi.fn(), vi.fn()))
      .rejects.toThrow("不会自动重发");
  });

  it("rejects out-of-order events", async () => {
    const wire = `event: started\ndata: {"sequence":2}\n\n`;
    await expect(streamQuestion(responseFromChunks([new TextEncoder().encode(wire)]), vi.fn(), vi.fn()))
      .rejects.toThrow("顺序异常");
  });

  it.each(["error", "cancelled"])("rejects %s after a partial answer", async (terminal) => {
    const events = [
      ["started", { sequence: 1 }],
      ["delta", { sequence: 2, delta: "未完成的回答" }],
      [terminal, { sequence: 3, ...(terminal === "error" ? { message: "AI_PROCESSING_FAILED" } : {}) }],
    ];
    const wire = events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify({ ...data as object, event: name, request_id: "r-1", contract_version: "0.2.0" })}\n\n`).join("");
    const delta = vi.fn();
    const sources = vi.fn();

    await expect(streamQuestion(responseFromChunks([new TextEncoder().encode(wire)]), delta, sources))
      .rejects.toThrow(terminal === "error" ? "AI_PROCESSING_FAILED" : "问答未能完成");
    if (terminal === "cancelled") {
      await expect(streamQuestion(responseFromChunks([new TextEncoder().encode(wire)]), vi.fn(), vi.fn()))
        .rejects.toHaveProperty("name", "AbortError");
    }
    expect(delta).toHaveBeenCalledExactlyOnceWith("未完成的回答");
    expect(sources).not.toHaveBeenCalled();
  });

  it.each(["error", "cancelled"])("accepts %s after provisional sources and cancels the reader", async (terminal) => {
    const cancel = vi.fn();
    const wire = ["started", "sources", terminal].map((event, index) =>
      `event: ${event}\ndata: ${JSON.stringify({ event, request_id: "r-1", contract_version: "0.2.0", sequence: index + 1, sources: [], has_answer: false })}\n\n`).join("");
    const response = new Response(new ReadableStream({
      start(controller) { controller.enqueue(new TextEncoder().encode(wire)); }, cancel,
    }));
    const sources = vi.fn();
    await expect(streamQuestion(response, vi.fn(), sources)).rejects.toThrow();
    expect(sources).toHaveBeenCalledExactlyOnceWith([], false);
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("surfaces an admission error without requiring started", async () => {
    const wire = 'event: error\ndata: {"sequence":1,"event":"error","request_id":"r-1","contract_version":"0.2.0","message":"QUESTION_REQUEST_CONFLICT"}\n\n';
    await expect(streamQuestion(responseFromChunks([new TextEncoder().encode(wire)]), vi.fn(), vi.fn()))
      .rejects.toThrow("QUESTION_REQUEST_CONFLICT");
  });

  it("completes and closes upstream without waiting for EOF", async () => {
    const cancel = vi.fn();
    const wire = ["started", "sources", "completed"].map((event, index) =>
      `event: ${event}\ndata: ${JSON.stringify({ event, request_id: "r-1", contract_version: "0.2.0", sequence: index + 1, sources: [], has_answer: false })}\n\n`).join("");
    const response = new Response(new ReadableStream({
      start(controller) { controller.enqueue(new TextEncoder().encode(wire)); }, cancel,
    }));
    const sources = vi.fn();
    await streamQuestion(response, vi.fn(), sources);
    expect(sources).toHaveBeenCalledExactlyOnceWith([], false);
    expect(cancel).toHaveBeenCalledOnce();
  });

  it.each([[true, 0], [false, 1], [true, 6]])("rejects inconsistent sources: has_answer=%s count=%s", async (hasAnswer, count) => {
    const wire = ["started", "sources", "completed"].map((event, index) =>
      `event: ${event}\ndata: ${JSON.stringify({ event, request_id: "r-1", contract_version: "0.2.0", sequence: index + 1, sources: Array.from({ length: Number(count) }, () => ({ source_id: "s-1" })), has_answer: hasAnswer })}\n\n`).join("");
    const sources = vi.fn();
    await expect(streamQuestion(responseFromChunks([new TextEncoder().encode(wire)]), vi.fn(), sources)).rejects.toThrow("状态异常");
    expect(sources).not.toHaveBeenCalled();
  });
});
