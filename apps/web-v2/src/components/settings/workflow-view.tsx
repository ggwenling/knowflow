"use client";

import Image from "next/image";
import { ArrowRight, FileText, Quote, ScanSearch } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import styles from "./settings.module.css";

const steps = [
  { number: "01", title: "上传资料", text: "支持 TXT、Markdown 与可读取文本的 PDF，单个文件不超过 8 MiB。", Icon: FileText },
  { number: "02", title: "建立索引", text: "解析、切分并写入向量索引；只有状态为“已就绪”的资料参与问答。", Icon: ScanSearch },
  { number: "03", title: "带引用回答", text: "每次提问独立检索，回答附最多 5 条原文依据，可逐条打开核对。", Icon: Quote },
];

export function WorkflowView() {
  return (
    <div className={styles.page}>
      <header className="workspace-header">
        <div>
          <p className={styles.eyebrow}>Workflows</p>
          <h1 data-display-heading>工作流</h1>
          <p>把多步检索与处理串成可复用的流程。该能力仍在开发中，当前版本只提供单轮问答。</p>
        </div>
        <span className={styles.plannedBadge} data-header-tag>开发中</span>
      </header>

      <div className={styles.workflowSteps}>
        {steps.map(({ number, title, text, Icon }) => (
          <article className={styles.step} key={number}>
            <span className={styles.stepNumber}>{number}</span>
            <Icon size={20} strokeWidth={1.5} aria-hidden="true" />
            <h2 data-display-heading>{title}</h2>
            <p>{text}</p>
          </article>
        ))}
      </div>

      <section className={`${styles.section} ${styles.workflowAvailable}`}>
        <Image className={styles.workflowArtwork} src="/atlas-workflow.webp" alt="" width={220} height={147} loading="lazy" />
        <h2 data-display-heading>当前可用能力</h2>
        <p className={styles.note}>
          工作流功能暂未开放。你可以先创建知识库、上传资料，再在对话页逐条提问；每一步都会保留可核验的原文来源。
        </p>
        <div className={styles.actions}>
          <ButtonLink href="/knowledge-bases">
            前往知识库 <ArrowRight size={16} aria-hidden="true" />
          </ButtonLink>
          <ButtonLink variant="secondary" href="/conversations">开始提问</ButtonLink>
        </div>
      </section>
    </div>
  );
}
