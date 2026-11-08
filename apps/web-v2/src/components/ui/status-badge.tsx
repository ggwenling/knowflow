import { documentStatusLabel, questionStatusLabel } from "@/lib/format";
import styles from "./status-badge.module.css";

type Tone = "ready" | "working" | "failed" | "cancelled" | "neutral";

const tones: Record<string, Tone> = {
  READY: "ready",
  SUCCEEDED: "ready",
  QUEUED: "working",
  RUNNING: "working",
  PROCESSING: "working",
  FAILED: "failed",
  CANCELLED: "cancelled",
};

export function StatusBadge({
  status,
  kind = "document",
  withDot = true,
}: {
  status: string;
  kind?: "document" | "question";
  withDot?: boolean;
}) {
  const tone = tones[status.toUpperCase()] ?? "neutral";
  const label = kind === "document" ? documentStatusLabel(status) : questionStatusLabel(status);
  return (
    <span className={`${styles.badge} ${styles[tone]}`}>
      {withDot && <span className={styles.dot} aria-hidden="true" />}
      {label}
    </span>
  );
}
