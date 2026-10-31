"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, isMockMode } from "../../lib/api-client";
import { mockApi } from "../../lib/mock";
import { ErrorBox, Loading } from "../../components/states";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const mock = isMockMode();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.includes("@")) {
      setError("请输入有效的邮箱地址。");
      return;
    }
    if (password.length < 12 || password.length > 128) {
      setError("密码长度候选为 12–128 字符（draft5 候选）。");
      return;
    }
    setBusy(true);
    try {
      if (mock) {
        await mockApi.login();
        window.localStorage.setItem("knowflow_token", "mock-token");
      } else if (mode === "login") {
        await api.login({ email, password });
      } else {
        await api.register({ email, password });
      }
      router.push("/libraries");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请检查邮箱与密码。");
    } finally {
      setBusy(false);
    }
  }

  async function onLogout() {
    if (mock) {
      window.localStorage.removeItem("knowflow_token");
    } else {
      await api.logout();
    }
    router.refresh();
  }

  const loggedIn =
    typeof window !== "undefined" && window.localStorage.getItem("knowflow_token");

  if (loggedIn) {
    return (
      <div>
        <h1>已登录</h1>
        <p className="muted">当前已有登录凭证（Mock 模式下为模拟凭证）。</p>
        <button className="secondary" onClick={onLogout}>
          退出登录
        </button>
      </div>
    );
  }

  return (
    <div>
      <h1>{mode === "login" ? "登录" : "注册"}</h1>
      <p className="muted">
        注册与登录使用邮箱 + 密码；成功后返回一次性显示的 Bearer 凭证，有效期 8 小时，无刷新令牌。
        令牌存放与 CSRF 策略为 draft5 尚待决定项，冻结前需复核。
      </p>
      {error ? <ErrorBox message={error} /> : null}
      <form onSubmit={onSubmit}>
        <label htmlFor="email">邮箱</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <label htmlFor="password">密码</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <div className="row" style={{ marginTop: 14 }}>
          <button type="submit" disabled={busy}>
            {busy ? "提交中…" : mode === "login" ? "登录" : "注册"}
          </button>
          <button type="button" className="secondary" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            切换到{mode === "login" ? "注册" : "登录"}
          </button>
        </div>
      </form>
      {busy ? <Loading label="正在提交…" /> : null}
    </div>
  );
}
