"use client";

import { useState, type ReactNode } from "react";

/** Mount on first use, then retain the dialog for exit motion and focus return. */
export function OnDemand({ open, children }: { open: boolean; children: ReactNode }) {
  const [activated, setActivated] = useState(open);
  if (open && !activated) setActivated(true);
  return open || activated ? children : null;
}
