"use client";

import { useEffect, useState, type ReactNode } from "react";

/** Let the form/shell paint before optional WebGL downloads and initialization. */
export function DeferredVisual({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let frame = 0;
    let idle: number | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const mount = () => { if (!cancelled) setReady(true); };
    frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        if ("requestIdleCallback" in window) idle = window.requestIdleCallback(mount, { timeout: 1000 });
        else timer = setTimeout(mount, 120);
      });
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      if (idle !== undefined) window.cancelIdleCallback(idle);
      if (timer !== undefined) clearTimeout(timer);
    };
  }, []);
  return ready ? children : null;
}
