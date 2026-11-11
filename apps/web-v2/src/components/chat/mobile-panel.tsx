"use client";

import type { ReactNode } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import styles from "./chat.module.css";

export function MobilePanel({ panel, onClose, children }: {
  panel: "history" | "docs" | null;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <Dialog open={panel !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent size="lg" className={styles.sheet}>
        <DialogTitle className={styles.sheetTitle}>{panel === "history" ? "对话历史" : "资料"}</DialogTitle>
        <DialogDescription className={styles.srOnly}>
          {panel === "history" ? "选择一条历史问答查看答案与来源。" : "当前知识库中的资料与索引状态。"}
        </DialogDescription>
        {children}
      </DialogContent>
    </Dialog>
  );
}
