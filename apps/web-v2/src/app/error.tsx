"use client";

import { useEffect } from "react";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("Workspace failed to render", error);
  }, [error]);

  return (
    <main style={{ display: "grid", minHeight: "100svh", placeItems: "center", padding: "32px" }}>
      <div style={{ maxWidth: 440 }}>
        <p style={{ margin: 0, color: "#8c8c8c", fontSize: 10, letterSpacing: ".18em", textTransform: "uppercase" }}>Something went wrong</p>
        <h1 style={{ margin: "10px 0 8px", fontFamily: "var(--font-serif)", fontSize: 36, fontWeight: 400, letterSpacing: "-.03em" }}>
          页面暂时无法显示
        </h1>
        <p style={{ margin: "0 0 18px", color: "#666", fontSize: 13, lineHeight: 1.8 }}>
          可以重试一次；如果问题持续，请刷新页面或稍后再回来。已保存的资料与问答记录不受影响。
        </p>
        <button
          onClick={reset}
          style={{ minHeight: 36, border: 0, borderRadius: 9, background: "#111", padding: "0 16px", color: "#fff", fontSize: 12, fontWeight: 600 }}
        >
          重试
        </button>
      </div>
    </main>
  );
}
