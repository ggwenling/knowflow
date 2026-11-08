/** Limits in-flight work and cancels queued work with its owning view. */
export class RequestScope {
  readonly controller = new AbortController();
  readonly signal = this.controller.signal;
  private running = 0;
  private queue: Array<{ start: () => void; reject: (reason: unknown) => void }> = [];

  private readonly concurrency: number;
  constructor(concurrency = 4) {
    if (!Number.isInteger(concurrency) || concurrency < 1) throw new RangeError("Invalid concurrency");
    this.concurrency = concurrency;
    this.signal.addEventListener("abort", () => {
      for (const item of this.queue.splice(0)) item.reject(this.signal.reason);
    }, { once: true });
  }

  run<T>(operation: () => Promise<T>, signal = this.signal): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const item = { start: () => {
        signal.removeEventListener("abort", cancel);
        if (signal.aborted || this.signal.aborted) { reject(signal.reason ?? this.signal.reason); this.drain(); return; }
        this.running++;
        Promise.resolve().then(operation).then(resolve, reject).finally(() => { this.running--; this.drain(); });
      }, reject: (reason: unknown) => { signal.removeEventListener("abort", cancel); reject(reason); } };
      const cancel = () => {
        const index = this.queue.indexOf(item);
        if (index >= 0) { this.queue.splice(index, 1); reject(signal.reason); }
      };
      if (signal.aborted || this.signal.aborted) { reject(signal.reason ?? this.signal.reason); return; }
      if (signal !== this.signal) signal.addEventListener("abort", cancel, { once: true });
      this.queue.push(item);
      this.drain();
    });
  }

  private drain() {
    while (!this.signal.aborted && this.running < this.concurrency && this.queue.length) this.queue.shift()!.start();
  }

  abort() { this.controller.abort(new DOMException("View changed", "AbortError")); }
}

export function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    const cancel = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", cancel); resolve(); }, ms);
    signal.addEventListener("abort", cancel, { once: true });
  });
}

export function waitUntilVisible(signal: AbortSignal): Promise<void> {
  if (typeof document === "undefined" || !document.hidden) return signal.aborted ? Promise.reject(signal.reason) : Promise.resolve();
  return new Promise((resolve, reject) => {
    const clean = () => { document.removeEventListener("visibilitychange", visible); signal.removeEventListener("abort", cancel); };
    const visible = () => { if (!document.hidden) { clean(); resolve(); } };
    const cancel = () => { clean(); reject(signal.reason); };
    signal.addEventListener("abort", cancel, { once: true });
    document.addEventListener("visibilitychange", visible);
    if (signal.aborted) cancel();
  });
}
