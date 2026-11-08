"use client";

import { useState, type DragEvent } from "react";
import { FilePicker } from "@/components/ui/file-picker";
import { Upload } from "lucide-react";
import styles from "./knowledge.module.css";

export function UploadZone({
  disabled,
  busy,
  onUpload,
}: {
  disabled?: boolean;
  busy?: boolean;
  onUpload: (file: File | undefined) => void;
}) {
  const [dragging, setDragging] = useState(false);

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (disabled || busy) return;
    const file = event.dataTransfer.files?.[0];
    if (file) onUpload(file);
  }

  return (
    <div
      className={`${styles.uploadZone} ${dragging ? styles.uploadDragging : ""}`}
      onDragOver={(event) => { event.preventDefault(); if (!disabled && !busy) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
    >
      <span className={styles.uploadIcon}>
        <Upload size={19} strokeWidth={1.5} aria-hidden="true" />
      </span>
      <div className={styles.uploadText}>
        <strong>{busy ? "正在上传并建立索引…" : "拖拽文件到这里，或选择文件"}</strong>
        <span>支持 TXT、Markdown 与可读取文本的 PDF · 单个文件最大 8 MiB · PDF 最多 200 页</span>
      </div>
      <FilePicker label="选择文件" className={styles.uploadAction} disabled={disabled || busy} onPick={onUpload} />
    </div>
  );
}
