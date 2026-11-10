import type { ReactNode } from "react";
import styles from "./recovery-view.module.css";

export function RecoveryView({ code, title, description, action }: { code: string; title: string; description: string; action: ReactNode }) {
  return (
    <main id="main-content" tabIndex={-1} className={styles.page}>
      <div className={`${styles.card} page-enter`}>
        <p className={styles.brand}>KnowFlow</p>
        <p className={styles.code}>{code}</p>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.description}>{description}</p>
        {action}
      </div>
    </main>
  );
}
