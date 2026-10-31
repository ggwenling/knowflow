import type { ReactNode } from "react";
import Link from "next/link";
import MockBanner from "../components/mock-banner";
import "./globals.css";

export const metadata = { title: "KnowFlow", description: "AI 私有知识库与智能文档助手（前端骨架预研）" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <nav>
          <Link href="/">KnowFlow</Link>
          <Link href="/login">登录</Link>
          <Link href="/libraries">知识库</Link>
          <Link href="/ask">问答</Link>
        </nav>
        <main>
          <MockBanner />
          {children}
        </main>
        <footer>
          前端骨架预研（KF2-008）：契约 DRAFT 0.2.0-draft.5 候选，未冻结；Mock 仅用于开发，不能代替真实端到端验收。
          重建入口在 KF2-004 冻结前不可公开，本骨架不提供重建入口。
        </footer>
      </body>
    </html>
  );
}
