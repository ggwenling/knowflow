"use client";

import { DropdownMenu } from "radix-ui";
import { useEffect, useRef } from "react";
import { MoreHorizontal } from "lucide-react";
import type { DocumentActionsProps } from "./document-actions";
import styles from "./knowledge.module.css";

export default function DocumentActionsMenu({ document, busy, onUpdate, onRebuild, onDelete, open, onOpenChange, initialFocus }: DocumentActionsProps & { open: boolean; onOpenChange: (open: boolean) => void; initialFocus?: "first" | "last" }) {
  const content = useRef<HTMLDivElement>(null);
  const focused = useRef(false);
  useEffect(() => {
    if (!open || focused.current || !initialFocus) return;
    const frame = requestAnimationFrame(() => {
      const items = content.current?.querySelectorAll<HTMLElement>('[role="menuitem"]');
      if (items?.length) { items[initialFocus === "last" ? items.length - 1 : 0].focus(); focused.current = true; }
    });
    return () => cancelAnimationFrame(frame);
  }, [open, initialFocus]);
  return (
    <DropdownMenu.Root open={open} onOpenChange={onOpenChange}>
      <div className={styles.docMenu}>
        <DropdownMenu.Trigger asChild>
          <button type="button" aria-label={`${document.original_name} 操作`} disabled={busy}><MoreHorizontal size={18} aria-hidden="true" /></button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content ref={content} className={styles.docMenuPanel} align="end" sideOffset={4}>
            <DropdownMenu.Item asChild onSelect={() => onUpdate(document)}><button type="button">更新资料</button></DropdownMenu.Item>
            <DropdownMenu.Item asChild onSelect={() => onRebuild(document)}><button type="button">重建索引</button></DropdownMenu.Item>
            <DropdownMenu.Item asChild onSelect={() => onDelete(document)}><button type="button" className={styles.dangerItem}>删除资料</button></DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </div>
    </DropdownMenu.Root>
  );
}
