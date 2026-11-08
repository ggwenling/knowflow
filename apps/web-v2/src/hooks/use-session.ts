"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ApiError, type User } from "@/services/api";
import { messageOf } from "@/lib/format";

const contractVersion = "0.2.0";

export function useSession() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    api<User>("me")
      .then((current) => {
        if (active) setUser(current);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if ((reason as ApiError).status === 401) setUser(null);
        else setError(messageOf(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  useEffect(() => {
    const expired = () => {
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
    try {
      await api(`auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ contract_version: contractVersion, email: email.trim(), password }),
      });
      const current = await api<User>("me");
      setUser(current);
      return null;
    } catch (reason) {
      return messageOf(reason);
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api("auth/logout", { method: "POST", body: "{}" });
    } catch {
      /* The proxy expires the cookie on its logout response. */
    } finally {
      setUser(null);
    }
  }, []);

  return { user, loading, error, retry, authenticate, signOut };
}
