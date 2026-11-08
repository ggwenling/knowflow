"use client";

import { useRef, useState, type DragEvent } from "react";
import { Upload } from "lucide-react";
import styles from "./knowledge.module.css";

const accepted = [".txt", ".md", ".pdf"];

export function UploadZone({
  disabled,
  busy,
  onUpload,
}: {
  disabled?: boolean;
  busy?: boolean;
  onUpload: (file: File | undefined) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function validate(file: File) {
    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!accepted.includes(extension)) {
      return false;
    }
    return true;
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (disabled || busy) return;
    const file = event.dataTransfer.files?.[0];
    if (file && validate(file)) onUpload(file);
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
      <label className={styles.uploadAction}>
        选择文件
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.md,.pdf"
          disabled={disabled || busy}
          onChange={(event) => {
            onUpload(event.target.files?.[0]);
            event.currentTarget.value = "";
          }}
        />
      </label>
    </div>
  );
}
