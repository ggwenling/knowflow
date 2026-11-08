"use client";

import type { ReactNode } from "react";
import { Toaster } from "sonner";
import { PerformanceReporter } from "./performance-reporter";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <>
      <PerformanceReporter />
      {children}
      <Toaster
        position="bottom-center"
        closeButton
        toastOptions={{
          style: {
            border: "1px solid var(--line)",
            borderRadius: "12px",
            background: "#ffffff",
            color: "var(--ink)",
            fontSize: "13px",
            boxShadow: "var(--shadow-pop)",
          },
        }}
      />
    </>
  );
}
