import Link from "next/link";
import { isMockMode } from "../lib/api-client";

export default function HomePage() {
  const mock = isMockMode();
  return (
    <div>
      <h1>KnowFlow</h1>
      <p className="muted">
        AI 私有知识库与智能文档助手。首版流程：上传真实资料 → 提出一个具体问题 → 查看支持回答的原文 →
        更新或删除文档后查询结果正确变化。每次提问独立检索，历史不作为多轮上下文。
      </p>
      <p>
        当前模式：
        <span className="tag">{mock ? "Mock（开发用）" : "真实接口"}</span>
      </p>
      <div className="card">
        <h2>开始</h2>
        <div className="row">
          <Link href="/login">登录</Link>
          <Link href="/libraries">知识库与上传</Link>
          <Link href="/ask">问答与来源核验</Link>
        </div>
      </div>
      <div className="card">
        <h2>本骨架尚未提供的能力</h2>
        <ul>
          <li>真实接口联调：需 KF2-004 冻结后以生成客户端替换 Mock。</li>
          <li>文档重建入口：KF2-004 冻结代次与幂等键前不可公开。</li>
          <li>历史问答页面、流式页面、PDF 页码预览：属后续任务（KF2-032/034），不在骨架范围。</li>
        </ul>
      </div>
    </div>
  );
}
