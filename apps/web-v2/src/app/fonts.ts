import localFont from "next/font/local";

// Reuse the existing self-hosted files and weights: preserve the shipped glyphs.
// Only the Latin display face is on the LCP path. Body weights load on use.
export const sans = localFont({
  src: [
    { path: "../../node_modules/@fontsource/dm-sans/files/dm-sans-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../../node_modules/@fontsource/dm-sans/files/dm-sans-latin-700-normal.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-dm-sans",
  display: "swap",
  preload: false,
  adjustFontFallback: "Arial",
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

export const cjkDisplay = localFont({
  src: "./fonts/noto-serif-sc-headings-400.woff2",
  variable: "--font-noto-serif-sc",
  weight: "400",
  // Never replace a painted Chinese heading late in the page's lifetime.
  display: "optional",
  preload: false,
  // next/font's Arial/Times metrics don't describe the system CJK serif faces.
  adjustFontFallback: false,
  fallback: ["Songti SC", "Noto Serif CJK SC", "serif"],
});
