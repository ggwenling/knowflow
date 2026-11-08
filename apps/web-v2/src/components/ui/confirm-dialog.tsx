"use client";

import { AlertDialog as Primitive } from "radix-ui";
import buttonStyles from "./button.module.css";
import styles from "./dialog.module.css";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "确认删除",
  cancelLabel = "取消",
  onConfirm,
  busy = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  busy?: boolean;
}) {
  return (
    <Primitive.Root open={open} onOpenChange={onOpenChange}>
      <Primitive.Portal>
        <Primitive.Overlay className={styles.overlay} />
        <Primitive.Content className={`${styles.content} ${styles.sm}`}>
          <Primitive.Title className={styles.title}>{title}</Primitive.Title>
          <Primitive.Description className={styles.description}>{description}</Primitive.Description>
          <div className={styles.actions}>
            <Primitive.Cancel className={`${buttonStyles.button} ${buttonStyles.secondary} ${buttonStyles.sm}`}>
              {cancelLabel}
            </Primitive.Cancel>
            <Primitive.Action
              className={`${buttonStyles.button} ${buttonStyles.danger} ${buttonStyles.sm}`}
              onClick={onConfirm}
              disabled={busy}
            >
              {confirmLabel}
            </Primitive.Action>
          </div>
        </Primitive.Content>
      </Primitive.Portal>
    </Primitive.Root>
  );
}
