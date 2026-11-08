"use client";

import { useRef, type ReactNode } from "react";
import { acceptedFileTypes } from "@/lib/upload-rules";

/** A native button keeps every upload entry point reachable by keyboard. */
export function FilePicker({ label, children, className, disabled, onPick }: {
  label: string;
  children?: ReactNode;
  className?: string;
  disabled?: boolean;
  onPick: (file: File | undefined) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className={className} aria-label={label} disabled={disabled} onClick={() => input.current?.click()}>
        {children ?? label}
      </button>
      <input ref={input} type="file" accept={acceptedFileTypes} hidden aria-label={label} onChange={(event) => {
        const file = event.target.files?.[0];
        event.currentTarget.value = "";
        if (file) onPick(file);
      }} />
    </>
  );
}
