"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, ShieldCheck } from "lucide-react";
import { useSessionContext, useKnowledgeContext } from "@/components/workspace/workspace-provider";
import { Button } from "@/components/ui/button";
import styles from "./settings.module.css";

export function SettingsView() {
  const router = useRouter();
  const session = useSessionContext();
  const knowledge = useKnowledgeContext();
  const [mode, setMode] = useState("unknown");

  useEffect(() => {
    fetch("/api/mode", { cache: "no-store" })
      .then((response) => response.json())
      .then((body: { mode?: string }) => setMode(body.mode ?? "unknown"))
      .catch(() => undefined);
  }, []);

  const modeLabel = mode === "synthetic" ? "合成模型（本地工程验证）" : mode === "external" ? "外部模型服务" : "尚未配置";

  return (
    <div className={`${styles.page} page-enter`}>
      <header className={styles.head}>
        <p className={styles.eyebrow}>Settings</p>
        <h1>设置</h1>
        <p>管理当前账户与工作区。容量、计费与团队协作暂未开放。</p>
      </header>

      <div className={styles.settingsGrid}>
        <section className={styles.section} aria-labelledby="account-title">
          <h2 id="account-title"><span className={styles.sectionIndex}>01</span> 账户</h2>
          <dl className={styles.rows}>
            <div className={styles.row}>
              <dt>登录邮箱</dt>
              <dd>{session.user?.email}</dd>
            </div>
            <div className={styles.row}>
              <dt>空间</dt>
              <dd>个人空间 · 仅自己可见</dd>
            </div>
            <div className={styles.row}>
              <dt>知识库</dt>
              <dd>{knowledge.bases.length} 个</dd>
            </div>
          </dl>
          <div className={styles.actions}>
            <Button variant="danger" size="sm" onClick={() => void session.signOut().then(() => router.replace("/login"))}>
              <LogOut size={14} aria-hidden="true" /> 退出登录
            </Button>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="model-title">
          <h2 id="model-title"><span className={styles.sectionIndex}>02</span> 模型与数据</h2>
          <dl className={styles.rows}>
            <div className={styles.row}>
              <dt>模型模式</dt>
              <dd>{modeLabel}</dd>
            </div>
            <div className={styles.row}>
              <dt>问答方式</dt>
              <dd>单轮问答 · 每次提问独立检索</dd>
            </div>
            <div className={styles.row}>
              <dt>资料范围</dt>
              <dd>文档片段与问题仅发送给当前配置的模型服务</dd>
            </div>
          </dl>
          <p className={styles.note}>
            <ShieldCheck size={14} aria-hidden="true" />
            合成模型只用于工程验证，不代表真实模型质量或费用；上传前请确认资料已获授权。
          </p>
        </section>
      </div>

      <section className={styles.section} aria-labelledby="unavailable-title">
        <h2 id="unavailable-title">暂未开放</h2>
        <p className={styles.note}>
          自助找回密码、团队协作、用量账单与导出功能仍在规划中。如需协助，请联系空间管理员。
        </p>
      </section>
    </div>
  );
}
