"use client";

import { useEffect, type ReactNode } from "react";
import { Toaster } from "sonner";
import { PerformanceReporter } from "./performance-reporter";

export function Providers({ children }: { children: ReactNode }) {
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      document.documentElement.dataset.input = "keyboard";
      if (event.key === "Escape") {
        document.querySelectorAll<HTMLDetailsElement>("details[data-popover][open]").forEach((popover) => {
          popover.open = false;
          popover.querySelector("summary")?.focus();
        });
      }
    };
    const pointer = (event: PointerEvent) => {
      document.documentElement.dataset.input = "pointer";
      document.querySelectorAll<HTMLDetailsElement>("details[data-popover][open]").forEach((popover) => {
        if (event.target instanceof Node && !popover.contains(event.target)) popover.open = false;
      });
    };
    document.addEventListener("keydown", keyboard, true);
    document.addEventListener("pointerdown", pointer, true);
    return () => {
      document.removeEventListener("keydown", keyboard, true);
      document.removeEventListener("pointerdown", pointer, true);
    };
  }, []);
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
            background: "var(--surface-overlay)",
            color: "var(--ink)",
            fontSize: "13px",
            boxShadow: "var(--shadow-pop)",
          },
        }}
      />
    </>
  );
}
