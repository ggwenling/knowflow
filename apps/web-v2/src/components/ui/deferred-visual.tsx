"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import "./deferred-visual.css";

/** Keep WebGL downloads/evaluation behind the initial paint, load and visibility. */
export function DeferredVisual({ children }: { children: ReactNode }) {
  const host = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let visible = false;
    let loaded = document.readyState === "complete";
    let cancelled = false;
    let idle: number | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // A minimum quiet paint window, even on cached loads where load/idle fire early.
    const earliest = performance.now() + 1800;
    function cancelPending() {
      if (idle !== undefined) window.cancelIdleCallback(idle);
      if (timer !== undefined) clearTimeout(timer);
      idle = undefined;
      timer = undefined;
    }
    function schedule() {
      cancelPending();
      if (cancelled || !loaded || !visible || document.hidden) return;
      timer = setTimeout(() => {
        const mount = () => {
          if (cancelled || !visible || document.hidden) return;
          cancelled = true;
          observer.disconnect();
          window.removeEventListener("load", onLoad);
          document.removeEventListener("visibilitychange", schedule);
          setReady(true);
        };
        if ("requestIdleCallback" in window) idle = window.requestIdleCallback(mount, { timeout: 1200 });
        else timer = setTimeout(mount, 16);
      }, Math.max(0, earliest - performance.now()));
    }
    const onLoad = () => { loaded = true; schedule(); };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      schedule();
    });
    observer.observe(element);
    window.addEventListener("load", onLoad, { once: true });
    document.addEventListener("visibilitychange", schedule);
    return () => {
      cancelled = true;
      cancelPending();
      observer.disconnect();
      window.removeEventListener("load", onLoad);
      document.removeEventListener("visibilitychange", schedule);
    };
  }, []);
  return <div className="deferred-visual" ref={host}>{ready ? children : null}</div>;
}
