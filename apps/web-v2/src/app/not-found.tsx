import Link from "next/link";

export default function NotFound() {
  return (
    <main style={{ display: "grid", minHeight: "100svh", placeItems: "center", padding: "32px" }}>
      <div style={{ maxWidth: 420 }}>
        <p style={{ margin: 0, color: "#8c8c8c", fontSize: 10, letterSpacing: ".18em", textTransform: "uppercase" }}>404</p>
        <h1 style={{ margin: "10px 0 8px", fontFamily: "var(--font-serif)", fontSize: 40, fontWeight: 400, letterSpacing: "-.03em" }}>
          找不到这个页面
        </h1>
        <p style={{ margin: "0 0 18px", color: "#666", fontSize: 13, lineHeight: 1.8 }}>
          链接可能已失效，或你没有访问权限。回到工作台继续查看知识库与问答记录。
        </p>
        <Link href="/" style={{ color: "#111", fontSize: 12, textDecoration: "underline", textUnderlineOffset: 3 }}>
          返回工作台
        </Link>
      </div>
    </main>
  );
}
