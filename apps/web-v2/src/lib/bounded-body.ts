/** Buffer atomically before forwarding: never send a partial over-limit upload.
 * A resizable backing store avoids retaining every chunk plus a final full copy.
 * Node 24 (the application's pinned runtime) supports resizable ArrayBuffer. */
export async function readBoundedBody(stream: ReadableStream<Uint8Array> | null, signal: AbortSignal, maxBytes: number, declaredLength = 0): Promise<Uint8Array<ArrayBuffer> | null> {
  if (!stream) return new Uint8Array();
  const initial = Math.min(maxBytes, 65536, Number.isFinite(declaredLength) && declaredLength > 0 ? declaredLength : 16384);
  const storage = new ArrayBuffer(initial, { maxByteLength: maxBytes });
  const bytes = new Uint8Array(storage);
  const reader = stream.getReader();
  let total = 0;
  let cancel!: () => void;
  const aborted = new Promise<never>((_, reject) => {
    cancel = () => reject(signal.reason ?? new DOMException("Request aborted", "AbortError"));
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
  });
  try {
    while (true) {
      const { value, done } = await Promise.race([reader.read(), aborted]);
      if (done) return bytes.subarray(0, total);
      if (value.byteLength > maxBytes - total) return null;
      const next = total + value.byteLength;
      if (next > storage.byteLength) storage.resize(Math.min(maxBytes, Math.max(next, storage.byteLength * 2)));
      bytes.set(value, total);
      total = next;
    }
  } finally {
    signal.removeEventListener("abort", cancel);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
