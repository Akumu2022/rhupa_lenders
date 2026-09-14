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

  const value = useMemo<AuthContextValue>(
    () => ({
      auth,
      login: (next) => {
        saveAuth(next);
        setAuth(next);
      },
      logout: () => {
        clearAuth();
        setAuth(null);
      },
    }),
    [auth],
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
