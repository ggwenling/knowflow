import { ImageResponse } from "next/og";
import { BrandSeal } from "@/components/ui/brand-seal";

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
          background: "#f7f4ed",
          padding: "72px 80px",
          color: "#17150f",
          fontFamily: "Georgia, serif",
        }}
      >
        <svg width="600" height="540" viewBox="0 0 600 540" style={{ position: "absolute", right: 0, top: 0 }}>
          {Array.from({ length: 28 }, (_, index) => (
            <path key={index} d={`M${90 + index * 7} 540 C${20 + index * 5} 280 ${510 - index * 3} 390 ${420 + index * 6} -40`} stroke="#655f55" strokeWidth="0.8" opacity="0.25" fill="none" />
          ))}
          <path d="M536 0v64h64" stroke="#c5b9a5" strokeWidth="1" fill="#eee9df" />
        </svg>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <BrandSeal size={40} />
          <span style={{ fontSize: 30, letterSpacing: "-0.02em" }}>KnowFlow</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <span style={{ fontSize: 92, lineHeight: 1, letterSpacing: "-0.035em" }}>Knowledge</span>
          <span style={{ fontSize: 92, lineHeight: 1, letterSpacing: "-0.035em" }}>that flows.</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", borderTop: "1px solid #dcd3c3", paddingTop: 22, fontFamily: "Arial, sans-serif", fontSize: 24, color: "#575249" }}>
          <span>智能知识管理与问答</span>
          <span>带原文引用的 RAG 工作台</span>
        </div>
      </div>
    ),
    size,
  );
}
