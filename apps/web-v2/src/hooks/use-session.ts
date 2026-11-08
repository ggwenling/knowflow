"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ApiError, type User } from "@/services/api";
import { messageOf } from "@/lib/format";

const contractVersion = "0.2.0";

export function useSession() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const generation = useRef(0);
  const lookup = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    const gen = ++generation.current;
    const request = new AbortController();
    lookup.current = request;
    api<User>("me", { signal: request.signal })
      .then((current) => {
        if (active && gen === generation.current) setUser(current);
      })
      .catch((reason: unknown) => {
        if (!active || gen !== generation.current || request.signal.aborted) return;
        if ((reason as ApiError).status === 401) setUser(null);
        else setError(messageOf(reason));
      })
      .finally(() => {
        if (active && gen === generation.current) setLoading(false);
      });
    return () => {
      active = false;
      request.abort();
    };
  }, [attempt]);

  useEffect(() => {
    const expired = () => {
      generation.current++;
      lookup.current?.abort();
      setUser(null);
      setLoading(false);
    };
    window.addEventListener("knowflow-session-expired", expired);
    return () => window.removeEventListener("knowflow-session-expired", expired);
  }, []);

  const retry = useCallback(() => {
    setLoading(true);
    setError("");
    setAttempt((value) => value + 1);
  }, []);

  const authenticate = useCallback(async (mode: "login" | "register", email: string, password: string) => {
    const gen = ++generation.current;
    lookup.current?.abort();
    try {
      await api(`auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ contract_version: contractVersion, email: email.trim(), password }),
      });
      const current = await api<User>("me");
      if (gen !== generation.current) return "登录状态已改变，请重试。";
      setUser(current);
      setLoading(false);
      setError("");
      return null;
    } catch (reason) {
      if (gen === generation.current) setLoading(false);
      return messageOf(reason);
    }
  }, []);

  const signOut = useCallback(async () => {
    generation.current++;
    lookup.current?.abort();
    try {
      await api("auth/logout", { method: "POST", body: "{}" });
    } catch {
      /* The proxy expires the cookie on its logout response. */
    } finally {
      setUser(null);
      setLoading(false);
    }
  }, []);

  return useMemo(() => ({ user, loading, error, retry, authenticate, signOut }), [user, loading, error, retry, authenticate, signOut]);
}
