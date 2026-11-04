"use client";

import { useEffect, useRef, type FormEvent, type ReactNode } from "react";
import { ArrowRight, Bell, CircleHelp, Database, FileText, Folder, Home, Layers, MessageSquare, Scale, Settings, Sparkles, Workflow } from "lucide-react";
import type { KnowledgeBase, QuestionHistory } from "@/lib/api";
import styles from "./dashboard.module.css";

type Props = {
  email: string;
  bases: KnowledgeBase[];
  selectedBase: string;
  history: QuestionHistory[];
  documentCount?: number;
  moreDocuments: boolean;
  draft: string;
  canAsk: boolean;
  busy: boolean;
  notice: string;
  modelNotice: ReactNode;
  onDismissNotice: () => void;
  onDraftChange: (value: string) => void;
  onAsk: (event: FormEvent<HTMLFormElement>) => void;
  onChooseBase: (id: string) => void;
  onOpenBase: (id: string) => void;
  onOpenHistory: (item: QuestionHistory) => void;
  onNavigate: (view: "chat" | "bases" | "documents") => void;
  onCreateBase: () => void;
  onSignOut: () => void;
};

const examples = [
  { text: "总结最新的产品功能", Icon: FileText },
  { text: "这份文档的核心结论是什么？", Icon: MessageSquare },
  { text: "对比 A 和 B 方案的区别", Icon: Scale },
];
const guide = [
  ["创建知识库", "为你的知识内容建立专属空间"],
  ["上传文档", "导入 PDF、TXT、Markdown 等资料"],
  ["开始提问", "基于知识库进行智能问答"],
];
const relativeTime = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });

function finishedLabel(finishedAt: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(finishedAt)) / 60_000));
  if (!Number.isFinite(minutes)) return "";
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return relativeTime.format(-minutes, "minute");
  if (minutes < 1440) return relativeTime.format(-Math.floor(minutes / 60), "hour");
  if (minutes < 10_080) return relativeTime.format(-Math.floor(minutes / 1440), "day");
  return new Date(finishedAt).toLocaleDateString("zh-CN");
}

function Wave() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const observer = new ResizeObserver(() => {
      const { clientWidth: width, clientHeight: height } = canvas;
      if (!width || !height) return;
      const scale = Math.min(devicePixelRatio, 2);
      canvas.width = width * scale;
      canvas.height = height * scale;
      context.scale(scale, scale);
      // The distant rows are compressed and fade into the hero background.
      for (let row = 0; row < 30; row++) {
        const depth = row / 29;
        const opacity = Math.sin(depth * Math.PI) * 0.095;
        context.fillStyle = "rgba(48, 48, 48, " + opacity + ")";
        for (let column = -4; column < width / 8 + 4; column++) {
          const x = column * 8 + depth * (16 + 45 * Math.sin(column / 26));
          const u = x / width;
          const left = Math.exp(-Math.pow((u - 0.13 - depth * 0.08) / 0.14, 2));
          const right = Math.exp(-Math.pow((u - 0.84 + depth * 0.1) / 0.12, 2));
          const mid = Math.exp(-Math.pow((u - 0.67) / 0.072, 2));
          const y = height * (0.59 + 0.38 * depth ** 1.4 - 0.46 * left - 0.35 * right - 0.13 * mid);
          context.beginPath();
          context.ellipse(x, y, 0.65 + depth * 0.65, 0.42 + depth * 0.18, -0.15, 0, Math.PI * 2);
          context.fill();
        }
      }
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);
  return <canvas ref={ref} className={styles.wave} aria-hidden="true" />;
}

export default function Dashboard({
  email, bases, selectedBase, history, documentCount, moreDocuments, draft, canAsk, busy, notice, modelNotice,
  onDismissNotice, onDraftChange, onAsk, onChooseBase, onOpenBase, onOpenHistory, onNavigate, onCreateBase, onSignOut,
}: Props) {
  const question = useRef<HTMLInputElement>(null);
  const guidePanel = useRef<HTMLElement>(null);
  return (
    <main className={styles.dashboard}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}><Layers size={24} aria-hidden="true" /><span>KnowFlow</span></div>
        <nav aria-label="工作台">
          <button aria-current="page"><Home />首页</button>
          <button onClick={() => onNavigate("chat")}><MessageSquare />对话</button>
          <button onClick={() => onNavigate("bases")}><Layers />知识库</button>
          <button onClick={() => onNavigate("documents")}><FileText />文档</button>
          <button disabled title="工作流暂不可用"><Workflow />工作流</button>
        </nav>
        <div className={styles.sidebarBottom}>
          <button disabled title="设置暂不可用"><Settings />设置</button>
          <button onClick={() => guidePanel.current?.focus()}><CircleHelp />帮助</button>
        </div>
      </aside>

      <section className={styles.content}>
        <Wave />
        <header className={styles.header}>
          <button disabled aria-label="通知暂不可用" title="通知暂不可用"><Bell size={24} /></button>
          <details className={styles.account}>
            <summary aria-label="账户菜单">{email.slice(0, 1).toUpperCase()}</summary>
            <div><span>{email}</span><button onClick={onSignOut}>退出</button></div>
          </details>
        </header>
        <div className={styles.hero}>
          <h1>KnowFlow</h1>
          <p>基于 RAG 的智能知识管理与问答系统</p>
        </div>
        {modelNotice}
        <form className={styles.ask} onSubmit={onAsk}>
          <label className={styles.scope}>
            <Database aria-hidden="true" />
            <select aria-label="选择知识库" value={selectedBase} onChange={(event) => onChooseBase(event.target.value)}>
              <option value="" disabled>选择知识库</option>
              {bases.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
          <Sparkles className={styles.askSpark} aria-hidden="true" />
          <input ref={question} aria-label="向知识库提问" value={draft} maxLength={4000} onChange={(event) => onDraftChange(event.target.value)} placeholder="向你的知识库提问..." />
          <button aria-label="提问" disabled={!canAsk || !draft.trim()} title={busy ? "正在生成回答" : !canAsk ? "资料就绪后即可提问" : undefined}><ArrowRight /></button>
        </form>
        <div className={styles.examples}>
          <span><Sparkles size={18} />例如：</span>
          {examples.map(({ text, Icon }) => <button key={text} onClick={() => { onDraftChange(text); question.current?.focus(); }}><Icon size={17} />{text}</button>)}
        </div>
        {notice && <div className={styles.notice} role="status">{notice}<button aria-label="关闭提示" onClick={onDismissNotice}>×</button></div>}

        <div className={styles.grid}>
          <div className={styles.overview}>
            <section aria-labelledby="base-preview">
              <div className={styles.sectionHeading}><h2 id="base-preview">我的知识库 <small>({bases.length})</small></h2>
                <button aria-label="查看全部知识库" onClick={() => onNavigate("bases")}>查看全部 <ArrowRight size={16} /></button>
              </div>
              {bases.length ? <div className={styles.cards}>
                {bases.slice(0, 3).map((base) => {
                  const count = base.id === selectedBase && documentCount != null
                    ? (moreDocuments ? "已加载 " : "") + documentCount + " 个文档" : "";
                  const updated = base.updated_at ? finishedLabel(base.updated_at) : "";
                  return <button key={base.id} onClick={() => onOpenBase(base.id)}>
                    <span className={styles.icon}><Folder size={21} /></span><ArrowRight className={styles.cardArrow} size={16} />
                    <strong>{base.name}</strong>
                    <small>{[count, updated && "更新于 " + updated].filter(Boolean).join(" · ") || "查看文档"}</small>
                  </button>;
                })}
              </div> : <p className={styles.empty}>这里还没有知识库。</p>}
            </section>

            <section className={styles.recent} aria-labelledby="recent-preview">
              <div className={styles.sectionHeading}><h2 id="recent-preview">最近对话</h2>
                <button aria-label="查看全部对话" onClick={() => onNavigate("chat")}>查看全部 <ArrowRight size={16} /></button>
              </div>
              {history.length ? history.slice(0, 3).map((item) => (
                <button className={styles.conversation} key={item.question_id} onClick={() => onOpenHistory(item)}>
                  <span className={styles.icon}><MessageSquare size={20} /></span><strong>{item.question}</strong>
                  <span>{item.finished_at ? finishedLabel(item.finished_at) : null}</span>
                </button>
              )) : <p className={styles.empty}>还没有对话，开始提问吧。</p>}
            </section>
          </div>
          <aside className={styles.guide} ref={guidePanel} tabIndex={-1} aria-labelledby="guide-title">
            <h2 id="guide-title">新手引导</h2>
            <p>三步上手 KnowFlow，<br />构建你的专属知识问答系统</p>
            <ol>{guide.map(([title, description], index) => (
              <li key={title}><span>{index + 1}</span><div><strong>{title}</strong><p>{description}</p></div></li>
            ))}</ol>
            <button onClick={onCreateBase}>创建知识库 <ArrowRight size={18} /></button>
          </aside>
        </div>
      </section>
    </main>
  );
}
