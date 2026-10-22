import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { clearAuth, loadAuth, saveAuth, tokenExpiryMs, type StoredAuth } from "./storage";

interface AuthContextValue {
  auth: StoredAuth | null;
  login: (auth: StoredAuth) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<StoredAuth | null>(() => loadAuth());
  const queryClient = useQueryClient();

  // Log out the moment the token expires, even if the tab is left open and idle.
  useEffect(() => {
    if (!auth) return;
    const expiry = tokenExpiryMs(auth.accessToken);
    if (expiry === null) return;
    const expire = () => {
      queryClient.clear();
      clearAuth();
      setAuth(null);
    };
    const remaining = expiry - Date.now();
    if (remaining <= 0) {
      expire();
      return;
    }
    // setTimeout caps at ~24.8 days; tokens are far shorter than that.
    const timer = window.setTimeout(expire, remaining);
    // Timers are throttled while a laptop sleeps — re-check when the tab wakes.
    const onVisible = () => {
      if (document.visibilityState === "visible" && expiry <= Date.now()) expire();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [auth, queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      auth,
      // Cached server data belongs to whoever was logged in. Drop it on every
      // login/logout so the next user on a shared branch computer never sees
      // the previous user's customers, even for a moment.
      login: (next) => {
        queryClient.clear();
        try {
          localStorage.removeItem("rupha.paymentsSeen"); // a new session starts with a fresh "seen" mark
        } catch {
          // ignore
        }
        saveAuth(next);
        setAuth(next);
      },
      logout: () => {
        queryClient.clear();
        clearAuth();
        setAuth(null);
      },
    }),
    [auth, queryClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
