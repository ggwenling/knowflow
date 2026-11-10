import type { ReactNode } from "react";
import Image from "next/image";
import styles from "./empty-state.module.css";

export function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
  illustration = false,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  compact?: boolean;
  illustration?: boolean;
}) {
  return (
    <div className={compact ? `${styles.empty} ${styles.compact}` : styles.empty}>
      {illustration ? <Image className={styles.illustration} src="/archive-study.webp" alt="" width={200} height={128} /> : icon && <span className={styles.icon}>{icon}</span>}
      <p className={styles.title}>{title}</p>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
