"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { ArrowRight, Folder, Home, Layers, MessageSquare, Settings, Workflow } from "lucide-react";
import { useSessionContext, useKnowledgeContext, useQuestionsContext } from "@/components/workspace/workspace-provider";
import { questionStatusLabel } from "@/lib/format";
import { allowSidebarTooltip, revealSidebarForCreate } from "@/lib/sidebar-preference";
import { BrandSeal } from "@/components/ui/brand-seal";
import { SidebarToggle } from "./sidebar-toggle";
import styles from "./app-shell.module.css";

const navItems = [
  { label: "首页", href: "/", Icon: Home, match: (path: string) => path === "/" },
  { label: "对话", href: "/conversations", Icon: MessageSquare, match: (path: string) => path.startsWith("/conversations") },
  { label: "知识库", href: "/knowledge-bases", Icon: Layers, match: (path: string) => path.startsWith("/knowledge-bases") },
  { label: "工作流", href: "/workflow", Icon: Workflow, match: (path: string) => path.startsWith("/workflow") },
  { label: "设置", href: "/settings", Icon: Settings, match: (path: string) => path.startsWith("/settings") },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const session = useSessionContext();
  const knowledge = useKnowledgeContext();
  const questions = useQuestionsContext();
  const [name, setName] = useState("");
  const [recentLimit, setRecentLimit] = useState(5);
  const inputRef = useRef<HTMLInputElement>(null);
  const accountRef = useRef<HTMLDetailsElement>(null);
  const libraryRef = useRef<HTMLDetailsElement>(null);
  const isChat = pathname.startsWith("/conversations");

  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const sync = () => { if (libraryRef.current) libraryRef.current.open = !media.matches; };
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (pathname === "/knowledge-bases" && new URLSearchParams(window.location.search).has("create")) {
      revealSidebarForCreate();
      if (libraryRef.current) libraryRef.current.open = true;
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [pathname]);

  async function createBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || knowledge.working || knowledge.loading) return;
    const outcome = await knowledge.create(trimmed);
    if (outcome.status === "stale") return;
    if (outcome.status === "failed") {
      toast.error("知识库未能创建，请稍后重试。");
      return;
    }
    setName("");
    toast.success(`已创建「${outcome.base.name}」`);
    router.push(`/knowledge-bases/${outcome.base.id}`);
  }

  function signOut() {
    if (accountRef.current) accountRef.current.open = false;
    void session.signOut();
  }

  const recent = questions.history.slice(0, recentLimit);

  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main-content" tabIndex={0}>跳到主要内容</a>

      <aside id="workspace-sidebar" className={`${styles.sidebar} ${pathname === "/" ? styles.homeSidebar : ""} ${isChat ? styles.chatSidebar : ""}`}>
        <div className={styles.brandRow}>
          <Link className={styles.brand} href="/" aria-label="KnowFlow 首页" translate="no">
            <BrandSeal size={28} />
            <span>
              KnowFlow
              <small>知识工作台</small>
            </span>
          </Link>
          <SidebarToggle />
        </div>

        <nav className={styles.nav} aria-label="主导航">
          <span className={styles.navIndicator} data-index={navItems.findIndex((item) => item.match(pathname))} aria-hidden="true" />
          {navItems.map(({ label, href, Icon, match }) => (
            <Link
              key={href}
              className={match(pathname) ? `${styles.navItem} ${styles.navActive}` : styles.navItem}
              href={href}
              aria-label={label}
              onFocus={allowSidebarTooltip}
              onPointerEnter={allowSidebarTooltip}
              aria-current={match(pathname) ? "page" : undefined}
            >
              <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
              <span className={styles.navLabel}>{label}</span>
              <span className={styles.railTooltip} role="tooltip" aria-label={label}>{label}</span>
            </Link>
          ))}
        </nav>

        <details className={styles.library} ref={libraryRef} open>
          <summary className={styles.mobileLibraryToggle}>工作区快捷入口 <span aria-hidden="true">＋</span></summary>
          <div className={styles.libraryContent}>
            <div className={styles.sectionHead}>
              <span>我的知识库</span>
              <Link href="/knowledge-bases" aria-label="打开全部知识库">
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <div className={styles.baseList}>
              {knowledge.bases.map((base) => (
                <Link
                  key={base.id}
                  className={knowledge.selectedBase === base.id ? `${styles.baseItem} ${styles.baseActive}` : styles.baseItem}
                  href={`/knowledge-bases/${base.id}`}
                  prefetch={false}
                >
                  <Folder size={16} strokeWidth={1.5} aria-hidden="true" />
                  <span>{base.name}</span>
                </Link>
              ))}
              {!knowledge.bases.length && <p className={styles.emptyHint}>还没有知识库，先建一个。</p>}
            </div>
            {pathname !== "/" && (
              <form className={styles.createForm} data-composite-field onSubmit={createBase}>
                <input
                  ref={inputRef}
                  id="new-base-name"
                  aria-label="新知识库名称"
                  name="name"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="新建知识库名称"
                  maxLength={200}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
                <button aria-label="创建知识库" aria-busy={knowledge.working || undefined} disabled={!name.trim() || knowledge.working || knowledge.loading}>
                  {knowledge.working ? "…" : "＋"}
                </button>
              </form>
            )}

            {!isChat && (
              <>
                <div className={styles.sectionHead}>
                  <span>最近问答</span>
                  <Link href="/conversations" aria-label="查看全部问答">
                    <ArrowRight size={16} aria-hidden="true" />
                  </Link>
                </div>
                <div className={styles.historyScroll}>
                  {recent.map((item) => (
                    <Link
                      key={item.question_id}
                      className={styles.historyItem}
                      href={`/conversations/${item.question_id}`}
                      prefetch={false}
                    >
                      <span>{item.question}</span>
                      <small>{questionStatusLabel(item.status)}</small>
                    </Link>
                  ))}
                  {!recent.length && <p className={styles.emptyHint}>还没有问答记录。</p>}
                  {(questions.hasMore || recentLimit < questions.history.length) && (
                    <button className={styles.moreButton} onClick={() => { setRecentLimit((limit) => limit + 50); if (recentLimit + 50 > questions.history.length) void questions.loadMore(); }} disabled={questions.loading}>
                      加载更多问答
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </details>

        <div className={styles.account}>
          <details className={styles.accountMenu} ref={accountRef} data-popover>
            <summary aria-label="账户菜单" aria-describedby="sidebar-account-tooltip" onFocus={allowSidebarTooltip} onPointerEnter={allowSidebarTooltip}>
              <span className={styles.avatar}>{session.user?.email.slice(0, 1).toUpperCase()}</span>
              <span id="sidebar-account-tooltip" className={styles.railTooltip} role="tooltip" aria-label={session.user?.email}>{session.user?.email}</span>
            </summary>
            <div className={styles.accountPopover}>
              <span className={styles.accountEmail}>{session.user?.email}</span>
              <Link href="/settings" onClick={() => { if (accountRef.current) accountRef.current.open = false; }}>
                账户设置 <ArrowRight size={16} aria-hidden="true" />
              </Link>
              <button onClick={signOut}>退出 <ArrowRight size={16} aria-hidden="true" /></button>
            </div>
          </details>
          <span className={styles.accountText}>
            {session.user?.email}
            <small>个人空间</small>
          </span>
          <button className={styles.signOut} onClick={signOut}>退出</button>
        </div>
      </aside>

      <div className={styles.mainColumn}>
        <main id="main-content" tabIndex={-1} className={styles.content}>{children}</main>
      </div>

      {(knowledge.error || questions.notice) && (
        <div className={styles.toasts}>
          {knowledge.error && (
            <div className={styles.errorToast} role="status">
              <span>{knowledge.error}</span>
              <button onClick={knowledge.clearError}>关闭</button>
            </div>
          )}
          {questions.notice && (
            <div className={styles.errorToast} role="alert">
              <span>{questions.notice}</span>
              <button onClick={() => void questions.load()} disabled={questions.loading}>重试</button>
              <button onClick={questions.clearNotice}>关闭</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
