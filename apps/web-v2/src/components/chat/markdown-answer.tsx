import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./chat.module.css";

export default function MarkdownAnswer({ text }: { text: string }) {
  return (
    <div className={styles.markdown}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>,
          // Never emit <img>: an answer containing ![](https://…) would otherwise make the
          // browser fetch a third-party URL as soon as it renders, leaking whatever the model
          // encoded into the path. Answers only ever cite text, so show the alt text instead.
          img: ({ alt }) => (
            <span className={styles.imageNote}>
              {alt?.trim() ? `（图片已省略：${alt.trim()}）` : "（图片已省略）"}
            </span>
          ),
          pre: ({ children }) => <pre className={styles.codeBlock}>{children}</pre>,
          code: ({ children, className }) => (
            <code className={className ?? styles.inlineCode}>{children}</code>
          ),
          table: ({ children }) => <div className={styles.tableWrap}><table>{children}</table></div>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
