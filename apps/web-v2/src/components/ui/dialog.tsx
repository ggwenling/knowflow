"use client";

import { Dialog as Primitive } from "radix-ui";
import { X } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";
import styles from "./dialog.module.css";

export const Dialog = Primitive.Root;
export const DialogTrigger = Primitive.Trigger;
export const DialogClose = Primitive.Close;
export const DialogTitle = Primitive.Title;
export const DialogDescription = Primitive.Description;

type ContentProps = ComponentProps<typeof Primitive.Content> & {
  size?: "sm" | "md" | "lg" | "wide";
  showClose?: boolean;
  closeLabel?: string;
  closeIcon?: ReactNode;
};

export function DialogContent({
  children,
  className,
  size = "md",
  showClose = true,
  closeLabel = "关闭",
  closeIcon,
  ...props
}: ContentProps) {
  return (
    <Primitive.Portal>
      <Primitive.Overlay className={styles.overlay} />
      <Primitive.Content className={cn(styles.content, styles[size], className)} {...props}>
        {showClose && (
          <Primitive.Close aria-label={closeLabel} className={styles.close}>
            {closeIcon ?? <X size={18} aria-hidden="true" />}
          </Primitive.Close>
        )}
        {children}
      </Primitive.Content>
    </Primitive.Portal>
  );
}
