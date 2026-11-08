import localFont from "next/font/local";

// Reuse the existing self-hosted files and weights: preserve the shipped glyphs.
// next/font emits early preload hints and metric-adjusted fallback faces.
export const sans = localFont({
  src: [
    { path: "../../node_modules/@fontsource/dm-sans/files/dm-sans-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../../node_modules/@fontsource/dm-sans/files/dm-sans-latin-700-normal.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-dm-sans",
  display: "swap",
  preload: true,
  fallback: ["PingFang SC", "Microsoft YaHei", "Arial", "sans-serif"],
});
export const serif = localFont({
  src: "../../node_modules/@fontsource/dm-serif-display/files/dm-serif-display-latin-400-normal.woff2",
  variable: "--font-dm-serif",
  weight: "400",
  display: "swap",
  preload: true,
  adjustFontFallback: "Times New Roman",
  fallback: ["Georgia", "Songti SC", "serif"],
});
