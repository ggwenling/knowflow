"use client";

import { useEffect, useSyncExternalStore } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { setSidebarCollapsed, sidebarCollapsed, subscribeSidebar } from "@/lib/sidebar-preference";
import styles from "./app-shell.module.css";

const serverSnapshot = () => false;

/** The preference subscription is local: toggling never updates the workspace tree. */
export function SidebarToggle() {
  const collapsed = useSyncExternalStore(subscribeSidebar, sidebarCollapsed, serverSnapshot);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        document.documentElement.dataset.sidebarTooltipDismissed = "true";
        return;
      }
      if (event.defaultPrevented || event.isComposing || event.repeat || event.altKey || event.shiftKey ||
        !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "b" ||
        !window.matchMedia("(min-width: 761px)").matches) return;
      event.preventDefault();
      setSidebarCollapsed(!sidebarCollapsed());
    };
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, []);

  return (
    <button type="button" className={styles.sidebarToggle} aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
      aria-expanded={!collapsed} aria-controls="workspace-sidebar" onClick={() => setSidebarCollapsed(!sidebarCollapsed())}>
      <PanelLeftClose size={18} strokeWidth={1.5} className={styles.collapseIcon} aria-hidden="true" />
      <PanelLeftOpen size={18} strokeWidth={1.5} className={styles.expandIcon} aria-hidden="true" />
    </button>
  );
}
