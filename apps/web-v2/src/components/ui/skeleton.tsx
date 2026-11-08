import styles from "./skeleton.module.css";

export function Skeleton({ height = 16, width = "100%", radius = 6 }: { height?: number; width?: number | string; radius?: number }) {
  return <span className={styles.skeleton} style={{ height, width, borderRadius: radius }} aria-hidden="true" />;
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className={styles.rows} role="status" aria-label="正在加载">
      {Array.from({ length: rows }, (_, index) => (
        <div className={styles.row} key={index}>
          <Skeleton height={38} width={38} radius={10} />
          <div className={styles.lines}>
            <Skeleton height={12} width="46%" />
            <Skeleton height={10} width="32%" />
          </div>
        </div>
      ))}
    </div>
  );
}
