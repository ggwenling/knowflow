import { Skeleton } from "./skeleton";
import { BrandSeal } from "./brand-seal";
import styles from "../workspace/workspace.module.css";

export function PageFallback({ label = "正在加载…" }: { label?: string }) {
  return (
    <div
      role="status"
      className={styles.loading}
    >
      <span className={styles.loadingBrand} aria-hidden="true"><BrandSeal /> KnowFlow</span>
      <p>{label}</p>
      <div className={styles.loadingLines} aria-hidden="true">
        <Skeleton height={8} width="100%" />
        <Skeleton height={8} width="72%" />
        <Skeleton height={8} width="42%" />
      </div>
    </div>
  );
}
