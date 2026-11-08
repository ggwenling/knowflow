export type Metric = { name: string; value: number; unit: "ms" | "count" | "score"; route: string; outcome?: "ok" | "failed" | "cancelled" };

export function metricRoute(path: string): string {
  const pathname = path.split("?", 1)[0];
  if (/^\/conversations\/[^/]+$/.test(pathname)) return "/conversations/[questionId]";
  if (/^\/knowledge-bases\/[^/]+$/.test(pathname)) return "/knowledge-bases/[baseId]";
  return ["/", "/login", "/register", "/settings", "/workflow", "/conversations", "/knowledge-bases"].includes(pathname) ? pathname : "/other";
}

/** Numeric, low-cardinality metrics only: no questions, sources, emails or IDs.
 * Consumers can listen for knowflow-performance; remote collection is opt-in. */
export function reportPerformance(name: string, value: number, unit: Metric["unit"] = "ms", outcome?: Metric["outcome"]) {
  if (typeof window === "undefined" || !Number.isFinite(value) || value < 0) return;
  const detail: Metric = { name, value, unit, route: metricRoute(window.location.pathname), ...(outcome ? { outcome } : {}) };
  window.dispatchEvent(new CustomEvent<Metric>("knowflow-performance", { detail }));
}
