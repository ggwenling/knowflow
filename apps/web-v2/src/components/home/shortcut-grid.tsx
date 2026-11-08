import Link from "next/link";
import { ArrowRight, FileText, MessageSquare, Plus, Workflow } from "lucide-react";
import styles from "./home-view.module.css";

const shortcuts = [
  { title: "创建知识库", description: "导入文档，构建专属知识库", Icon: Plus, href: "/knowledge-bases?create=1" },
  { title: "新建对话", description: "基于知识库进行智能问答", Icon: MessageSquare, href: "/conversations" },
  { title: "上传文档", description: "支持 PDF、TXT、Markdown", Icon: FileText, href: "" },
  { title: "创建工作流", description: "串联检索与处理步骤", Icon: Workflow, href: "/workflow" },
] as const;

export function ShortcutGrid({ uploadHref }: { uploadHref: string }) {
  return (
    <div className={styles.shortcuts} aria-label="快捷操作">
      {shortcuts.map(({ title, description, Icon, href }, index) => (
        <Link
          key={title}
          className={styles.shortcut}
          href={href || uploadHref}
          aria-label={title}
          style={{ animationDelay: `${80 + index * 45}ms` }}
        >
          <Icon className={styles.shortcutIcon} size={26} strokeWidth={1.5} aria-hidden="true" />
          <span className={styles.shortcutText}>
            <strong>{title}</strong>
            <small>{description}</small>
          </span>
          <ArrowRight className={styles.shortcutArrow} size={17} strokeWidth={1.6} aria-hidden="true" />
        </Link>
      ))}
    </div>
  );
}
