"use client";

import Image from "next/image";
import { BrandSeal } from "@/components/ui/brand-seal";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useSession } from "@/hooks/use-session";
import styles from "./auth-view.module.css";
import { DeferredVisual } from "@/components/ui/deferred-visual";
import { BackgroundMotionToggle } from "@/components/ui/background-motion-toggle";

const Ribbon = dynamic(() => import("@/components/login-ribbon"), { ssr: false });

export function AuthView({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const session = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [resetHelp, setResetHelp] = useState(false);
  const [motionPaused, setMotionPaused] = useState(false);

  useEffect(() => {
    if (session.user) router.replace("/");
  }, [router, session.user]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const failure = await session.authenticate(mode, email, password);
    setBusy(false);
    if (failure) {
      setError(failure);
      requestAnimationFrame(() => document.getElementById("auth-password")?.focus());
      return;
    }
    setPassword("");
    setShowPassword(false);
    router.replace("/");
  }

  return (
    <main id="main-content" tabIndex={-1} className={styles.page} lang="en">
      <div className={styles.artPanel} aria-hidden="true">
        <Image className={styles.atlasArt} src="/atlas-auth.webp" alt="" width={720} height={1080} preload sizes="(max-width: 700px) 1px, 54vw" />
        <div className={`loginFlow ${styles.ribbon}`}>
          <DeferredVisual><Ribbon paused={motionPaused} /></DeferredVisual>
        </div>
      </div>
      <div className={styles.motionControl}>
        <BackgroundMotionToggle english paused={motionPaused} onToggle={() => setMotionPaused((paused) => !paused)} />
      </div>
      <section key={mode} className={styles.content}>
        <div className={styles.brand} translate="no"><BrandSeal size={32} />KnowFlow</div>
        <div className={styles.intro} data-ink-settle>
          <h1>
            {mode === "login" ? <>Knowledge<br />that flows.</> : <>Create your<br />account.</>}
          </h1>
          <p className={styles.lead}>
            {mode === "login"
              ? <>Sign in to KnowFlow and keep your<br className={styles.break} /> knowledge in motion.</>
              : "Create an account to start building your knowledge base."}
          </p>
        </div>

        <div className={styles.formGroup}>
          <form className={styles.form} onSubmit={submit} noValidate={false} aria-busy={busy}>
            <label htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              name="email"
              type="email"
              placeholder="name@example.com"
              autoComplete="email"
              spellCheck={false}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "auth-error" : undefined}
              required
              disabled={session.loading || busy}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <label htmlFor="auth-password">Password</label>
            <div className={styles.passwordField}>
              <input
                id="auth-password"
                name="password"
                type={showPassword ? "text" : "password"}
                placeholder="At least 12 characters"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={12}
                maxLength={128}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? "auth-error" : mode === "register" ? "auth-password-hint" : undefined}
                required
                disabled={session.loading || busy}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                type="button"
                aria-controls="auth-password"
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((value) => !value)}
              >
                {showPassword ? <EyeOff size={20} aria-hidden="true" /> : <Eye size={20} aria-hidden="true" />}
              </button>
            </div>
            {mode === "register" && <small id="auth-password-hint" className={styles.hint}>Use 12–128 characters.</small>}
            {error && <p id="auth-error" className={styles.error} lang="zh-CN" role="alert">{error}</p>}
            <button className={styles.submit} disabled={session.loading || busy} aria-busy={session.loading || busy}>
              {busy && <span className={styles.spinner} aria-hidden="true" />}
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className={styles.links}>
            {mode === "login" && (
              <button type="button" onClick={() => setResetHelp((value) => !value)} aria-expanded={resetHelp}>
                Forgot password?
              </button>
            )}
            <Link
              href={mode === "login" ? "/register" : "/login"}
              onClick={() => { setError(""); setPassword(""); setShowPassword(false); setResetHelp(false); }}
            >
              {mode === "login" ? "Create an account" : "Back to sign in"}
            </Link>
          </div>
          {resetHelp && (
            <p className={styles.resetHelp} role="status">
              Self-service password reset is currently unavailable.
            </p>
          )}
        </div>
      </section>
      <p className={styles.footnote}>KnowFlow · Retrieval-augmented knowledge workspace</p>
    </main>
  );
}
