import type { ReactNode } from "react";
import { StaticArt } from "@/components/ui/static-art";
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
  illustration?: boolean | "bases" | "documents" | "history";
}) {
  return (
    <div className={compact ? `${styles.empty} ${styles.compact}` : styles.empty}>
      {illustration ? <StaticArt className={styles.illustration} src={`/atlas-empty-${typeof illustration === "string" ? illustration : "bases"}.webp`} alt="" width={200} height={134} loading="lazy" /> : icon && <span className={styles.icon}>{icon}</span>}
      <p data-display-heading className={styles.title}>{title}</p>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
