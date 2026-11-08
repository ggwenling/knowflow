import type { Metadata } from "next";
import { AuthView } from "@/components/auth/auth-view";

export const metadata: Metadata = { title: "创建账户" };

export default function Page() {
  return <AuthView mode="register" />;
}
