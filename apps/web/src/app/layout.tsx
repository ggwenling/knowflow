import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "KnowFlow · 文档核验工作台",
  description: "基于个人技术文档的问答与原文核验。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
