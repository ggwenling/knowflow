"use client";

import { useEffect } from "react";
import { RecoveryView } from "@/components/ui/recovery-view";
import styles from "@/components/ui/recovery-view.module.css";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error("Workspace failed to render", error); }, [error]);
  return <RecoveryView code="Something went wrong" title="页面暂时无法显示" description="可以重试一次；如果问题持续，请刷新页面或稍后再回来。已保存的资料与问答记录不受影响。" action={<button onClick={reset} className={styles.action}>重试 <span aria-hidden="true">↻</span></button>} />;
}
