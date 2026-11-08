"use client";

import { useEffect } from "react";
import { useReportWebVitals } from "next/web-vitals";
import { metricRoute, reportPerformance, type Metric } from "@/lib/performance";

const names = new Set(["CLS", "FCP", "INP", "LCP", "TTFB", "api_request", "api_headers_ms", "question_first_delta_ms", "question_duration_ms", "upload_accept_ms", "index_wait_ms"]);
const reportVital: Parameters<typeof useReportWebVitals>[0] = (metric) => reportPerformance(metric.name, metric.value, metric.name === "CLS" ? "score" : "ms");

export function PerformanceReporter() {
  useReportWebVitals(reportVital);
  useEffect(() => {
    const configured = process.env.NEXT_PUBLIC_PERFORMANCE_ENDPOINT;
    // Collection is opt-in and restricted to a configured same-origin receiver.
    if (!configured?.startsWith("/") || configured.startsWith("//")) return;
    let receiver: URL;
    try { receiver = new URL(configured, window.location.origin); } catch { return; }
    if (receiver.origin !== window.location.origin) return;
    const endpoint = receiver.pathname + receiver.search;
    const queue: Metric[] = [];
    const flush = () => {
      if (!queue.length) return;
      const body = JSON.stringify({ metrics: queue.splice(0) });
      if (navigator.sendBeacon) navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }));
      else void fetch(endpoint, { method: "POST", headers: { "content-type": "application/json" }, body, keepalive: true, credentials: "same-origin" }).catch(() => {});
    };
    const receive = (event: Event) => {
      const value = (event as CustomEvent<Metric>).detail;
      if (!value || !names.has(value.name) || !Number.isFinite(value.value) || value.value < 0) return;
      if (!["ms", "count", "score"].includes(value.unit)) return;
      const outcome = ["ok", "failed", "cancelled"].includes(value.outcome ?? "") ? value.outcome : undefined;
      queue.push({ name: value.name, value: value.value, unit: value.unit, route: typeof value.route === "string" ? metricRoute(value.route) : "/other", ...(outcome ? { outcome } : {}) });
      if (queue.length >= 20) flush();
    };
    const visibility = () => { if (document.hidden) flush(); };
    window.addEventListener("knowflow-performance", receive);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", flush);
    return () => { window.removeEventListener("knowflow-performance", receive); document.removeEventListener("visibilitychange", visibility); window.removeEventListener("pagehide", flush); flush(); };
  }, []);
  return null;
}
