import type { ComponentProps } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import styles from "./button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "text";
type Size = "sm" | "md" | "lg";

export function ButtonLink({ variant = "primary", size = "md", className, ...props }: ComponentProps<typeof Link> & { variant?: Variant; size?: Size }) {
  return <Link className={cn(styles.button, styles[variant], styles[size], className)} {...props} />;
}

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
