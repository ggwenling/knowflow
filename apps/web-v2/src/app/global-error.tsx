"use client";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="zh-CN">
      <body style={{ margin: 0, background: "#fff", color: "#111", fontFamily: '"DM Sans", "PingFang SC", "Microsoft YaHei", sans-serif' }}>
        <main style={{ display: "grid", minHeight: "100svh", placeItems: "center", padding: "32px" }}>
          <div style={{ maxWidth: 440 }}>
            <h1 style={{ margin: 0, fontFamily: "Georgia, serif", fontSize: 34, fontWeight: 400 }}>KnowFlow 暂时不可用</h1>
            <p style={{ margin: "10px 0 18px", color: "#666", fontSize: 13, lineHeight: 1.8 }}>
              应用没有完成加载。请重试；如果仍然失败，请刷新页面。{error.digest ? ` 错误标识：${error.digest}` : ""}
            </p>
            <button
              onClick={reset}
              style={{ minHeight: 36, border: 0, borderRadius: 9, background: "#111", padding: "0 16px", color: "#fff", fontSize: 12, fontWeight: 600 }}
            >
              重试
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
