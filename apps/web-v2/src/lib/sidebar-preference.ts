export const SIDEBAR_STORAGE_KEY = "knowflow.sidebar.collapsed";
const changeEvent = "knowflow-sidebar-change";

/** Read before paint; the client store uses the same attribute, not a second state. */
export const sidebarBootstrap = `try{document.documentElement.dataset.sidebarCollapsed=localStorage.getItem("${SIDEBAR_STORAGE_KEY}")==="true"?"true":"false"}catch{document.documentElement.dataset.sidebarCollapsed="false"}`;

export function sidebarCollapsed() {
  return typeof document !== "undefined" && document.documentElement.dataset.sidebarCollapsed === "true";
}

export function setSidebarCollapsed(collapsed: boolean) {
  document.documentElement.dataset.sidebarCollapsed = String(collapsed);
  try { localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed)); } catch { /* Storage can be unavailable; this tab still works. */ }
  window.dispatchEvent(new Event(changeEvent));
}

export function allowSidebarTooltip() {
  delete document.documentElement.dataset.sidebarTooltipDismissed;
}

export function subscribeSidebar(listener: () => void) {
  const storage = (event: StorageEvent) => {
    if (event.key !== SIDEBAR_STORAGE_KEY && event.key !== null) return;
    document.documentElement.dataset.sidebarCollapsed = event.newValue === "true" ? "true" : "false";
    listener();
  };
  window.addEventListener(changeEvent, listener);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener(changeEvent, listener);
    window.removeEventListener("storage", storage);
  };
}

export function revealSidebarForCreate() {
  if (window.matchMedia("(min-width: 761px)").matches && sidebarCollapsed()) setSidebarCollapsed(false);
}
