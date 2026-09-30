import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { clearAuth, loadAuth, saveAuth, type StoredAuth } from "./storage";

interface AuthContextValue {
  auth: StoredAuth | null;
  login: (auth: StoredAuth) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<StoredAuth | null>(() => loadAuth());
  const queryClient = useQueryClient();

  const value = useMemo<AuthContextValue>(
    () => ({
      auth,
      // Cached server data belongs to whoever was logged in. Drop it on every
      // login/logout so the next user on a shared branch computer never sees
      // the previous user's customers, even for a moment.
      login: (next) => {
        queryClient.clear();
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
