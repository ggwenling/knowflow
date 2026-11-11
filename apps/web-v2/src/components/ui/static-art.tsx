import type { ComponentProps } from "react";

/** Pre-sized local WebP art: no image optimizer or image client runtime needed. */
export function StaticArt(props: ComponentProps<"img"> & { width: number; height: number }) {
  // eslint-disable-next-line @next/next/no-img-element -- these small, compressed assets are already sized for their slots
  return <img decoding="async" {...props} alt={props.alt ?? ""} />;
}
