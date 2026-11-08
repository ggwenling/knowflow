import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { WorkspaceProvider } from "@/components/workspace/workspace-provider";
import { StoreProvider } from "@/components/store";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <StoreProvider>
      <WorkspaceProvider>
        <AppShell>{children}</AppShell>
      </WorkspaceProvider>
    </StoreProvider>
  );
}
