"use client";

import type { ReactNode } from "react";
import { Toaster } from "sonner";
import { StoreProvider } from "./store";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <StoreProvider>
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
    </StoreProvider>
  );
}
