import { describe, expect, it, vi } from "vitest";
import { streamQuestion } from "@/lib/api";

function responseFromChunks(chunks: Uint8Array[]) {
  return new Response(new ReadableStream({
    start(controller) { for (const chunk of chunks) controller.enqueue(chunk); controller.close(); },
  }), { headers: { "content-type": "text/event-stream" } });
}

describe("streamQuestion", () => {
  it("decodes split UTF-8 frames, keeps source events and waits for completed", async () => {
    const body = [
      { sequence: 1, request_id: "r-1" },
      { sequence: 2, delta: "引用中文" },
      { sequence: 3, sources: [{ source_id: "s-1" }] },
      { sequence: 4 },
    ];
    const wire = body.map((item, index) => `event: ${["started", "delta", "sources", "completed"][index]}\ndata: ${JSON.stringify(item)}\n\n`).join("");
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
    const wire = `event: started\ndata: {"sequence":1}\n\n`;
    await expect(streamQuestion(responseFromChunks([new TextEncoder().encode(wire)]), vi.fn(), vi.fn()))
      .rejects.toThrow("不会自动重发");
  });

  it("rejects out-of-order events", async () => {
    const wire = `event: started\ndata: {"sequence":2}\n\n`;
    await expect(streamQuestion(responseFromChunks([new TextEncoder().encode(wire)]), vi.fn(), vi.fn()))
      .rejects.toThrow("顺序异常");
  });
});
