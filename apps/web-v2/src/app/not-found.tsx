import Link from "next/link";
import { RecoveryView } from "@/components/ui/recovery-view";
import styles from "@/components/ui/recovery-view.module.css";

export default function NotFound() {
  return <RecoveryView code="404 / Page not found" title="找不到这个页面" description="链接可能已失效，或你没有访问权限。回到工作台继续查看知识库与问答记录。" action={<Link href="/" className={styles.action}>返回工作台 <span aria-hidden="true">↗</span></Link>} />;
}
