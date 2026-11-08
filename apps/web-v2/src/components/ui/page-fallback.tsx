export function PageFallback() {
  return (
    <div
      role="status"
      style={{
        display: "grid",
        minHeight: "40svh",
        placeItems: "center",
        color: "#8c8c8c",
        fontSize: 13,
      }}
    >
      正在加载…
    </div>
  );
}
