import type { Metadata } from "next";
import { AuthView } from "@/components/auth/auth-view";

export const metadata: Metadata = { title: "登录" };

export default function Page() {
  return <AuthView mode="login" />;
}
