import { ImageResponse } from "next/og";

export const alt = "KnowFlow · 智能知识工作台";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          width: "100%",
          height: "100%",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#ffffff",
          padding: "72px 80px",
          color: "#111111",
          fontFamily: "Georgia, serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ width: 22, height: 22, borderRadius: 999, background: "#111111" }} />
          <span style={{ fontSize: 26, letterSpacing: "0.12em", textTransform: "uppercase" }}>KnowFlow</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <span style={{ fontSize: 92, lineHeight: 1, letterSpacing: "-0.035em" }}>Knowledge</span>
          <span style={{ fontSize: 92, lineHeight: 1, letterSpacing: "-0.035em" }}>that flows.</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", borderTop: "1px solid #eaeaea", paddingTop: 22, fontFamily: "Arial, sans-serif", fontSize: 24, color: "#666666" }}>
          <span>智能知识管理与问答</span>
          <span>带原文引用的 RAG 工作台</span>
        </div>
      </div>
    ),
    size,
  );
}
