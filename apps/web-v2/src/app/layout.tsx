import type { Metadata, Viewport } from "next";
import { sans, serif } from "./fonts";
import "./globals.css";
import { Providers } from "@/components/providers";
import { sidebarBootstrap } from "@/lib/sidebar-preference";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: {
    default: "KnowFlow · 智能知识工作台",
    template: "%s · KnowFlow",
  },
  description: "基于 RAG 的智能知识管理与问答系统。上传资料、建立索引，并带着可核验的原文引用回答问题。",
  applicationName: "KnowFlow",
  keywords: ["知识库", "RAG", "问答", "文档检索", "KnowFlow"],
  openGraph: {
    title: "KnowFlow · 智能知识工作台",
    description: "上传资料，建立索引，带着原文引用回答问题。",
    type: "website",
    locale: "zh_CN",
  },
  twitter: {
    card: "summary_large_image",
    title: "KnowFlow · 智能知识工作台",
    description: "上传资料，建立索引，带着原文引用回答问题。",
  },
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  colorScheme: "light",
  viewportFit: "cover",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className={`${sans.variable} ${serif.variable}`} suppressHydrationWarning>
      <head>
        <script id="sidebar-preference" dangerouslySetInnerHTML={{ __html: sidebarBootstrap }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
