"use client";

import { useSyncExternalStore } from "react";
import styles from "./settings.module.css";

const sections = [
  { id: "settings-account", label: "账户" },
  { id: "settings-model", label: "模型与数据" },
  { id: "settings-unavailable", label: "暂未开放" },
] as const;
const serverSnapshot = () => sections[0].id;
const snapshot = () => sections.find(({ id }) => `#${id}` === window.location.hash)?.id ?? sections[0].id;
const subscribe = (listener: () => void) => {
  window.addEventListener("hashchange", listener);
  return () => window.removeEventListener("hashchange", listener);
};

/** Native anchors retain history and focus; only this index subscribes to the hash. */
export function SettingsNav() {
  const active = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  return (
    <nav className={styles.sectionNav} aria-label="设置分区">
      {sections.map(({ id, label }) => (
        <a key={id} href={`#${id}`} aria-current={active === id ? "location" : undefined}>{label}</a>
      ))}
    </nav>
  );
}
