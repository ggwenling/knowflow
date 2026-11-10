import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";
import styles from "./button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "text";
type Size = "sm" | "md" | "lg";

export function Button({
  variant = "primary",
  size = "md",
  full = false,
  loading = false,
  disabled,
  children,
  className,
  ...props
}: ComponentProps<"button"> & { variant?: Variant; size?: Size; full?: boolean; loading?: boolean }) {
  return (
    <button
      className={cn(styles.button, styles[variant], styles[size], full && styles.full, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <span className={styles.loader} aria-hidden="true" />}
      {children}
    </button>
  );
}
