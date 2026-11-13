import type { ReactNode } from "react";

/** Next remounts the route template while retaining the shell and domain providers. */
export default function WorkspaceTemplate({ children }: { children: ReactNode }) {
  return <div className="workspace-route">{children}</div>;
}
