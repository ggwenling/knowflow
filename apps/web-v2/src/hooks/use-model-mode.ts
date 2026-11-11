"use client";

import { useCallback, useEffect, useState } from "react";
import type { ModelMode } from "@/lib/model-mode";

let cached: ModelMode | null = null;
let pending: Promise<ModelMode> | null = null;

function readMode() {
  if (cached) return Promise.resolve(cached);
  if (pending) return pending;
  pending = fetch("/api/mode", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("Model mode request failed");
      return response.json() as Promise<{ mode?: string }>;
    })
    .then((body) => {
      cached = body.mode === "synthetic" || body.mode === "external" ? body.mode : "unknown";
      return cached;
    })
    .finally(() => { pending = null; });
  return pending;
}

export function useModelMode(initialMode?: ModelMode) {
  const [mode, setMode] = useState<ModelMode>(initialMode ?? cached ?? "unknown");
  const [loading, setLoading] = useState(initialMode === undefined && cached === null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async (force = false) => {
    if (force) cached = null;
    setLoading(true);
    setFailed(false);
    try {
      const next = await readMode();
      setMode(next);
      return next;
    } catch {
      setMode("unknown");
      setFailed(true);
      return "unknown" as const;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialMode !== undefined) return;
    queueMicrotask(() => { void load(); });
  }, [initialMode, load]);

  const retry = useCallback(() => { void load(true); }, [load]);
  return { mode, loading, failed, retry };
}
