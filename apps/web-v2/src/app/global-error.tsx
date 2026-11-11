"use client";

import { RecoveryView } from "@/components/ui/recovery-view";
import styles from "@/components/ui/recovery-view.module.css";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="zh-CN" style={{ colorScheme: "light" }}>
      <body style={{ margin: 0, background: "#f7f4ed" }}>
        <RecoveryView code="Workspace unavailable" title="KnowFlow 暂时不可用" description={`应用没有完成加载。请重试；如果仍然失败，请刷新页面。${error.digest ? ` 错误标识：${error.digest}` : ""}`} action={<button onClick={reset} className={styles.action}>重试 <span aria-hidden="true">↻</span></button>} />
      </body>
    </html>
  );
}
