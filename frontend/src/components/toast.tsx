import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type ToastKind = "success" | "error" | "info";
interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

const ToastContext = createContext<((message: string, kind?: ToastKind) => void) | null>(null);

const TOAST_STYLES: Record<ToastKind, string> = {
  success: "border-emerald-200 bg-white text-emerald-800 dark:border-emerald-900/60 dark:bg-slate-800 dark:text-emerald-300",
  error: "border-rose-200 bg-white text-rose-800 dark:border-rose-900/60 dark:bg-slate-800 dark:text-rose-300",
  info: "border-indigo-200 bg-white text-indigo-800 dark:border-indigo-900/60 dark:bg-slate-800 dark:text-indigo-300",
};

const TOAST_DOT: Record<ToastKind, string> = {
  success: "bg-emerald-500",
  error: "bg-rose-500",
  info: "bg-indigo-500",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const push = useCallback((message: string, kind: ToastKind = "success") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, kind }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex flex-col items-center gap-2 px-4 sm:items-end sm:right-4 sm:left-auto">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`animate-toast-in pointer-events-auto flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium shadow-lg ${TOAST_STYLES[toast.kind]}`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${TOAST_DOT[toast.kind]}`} />
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Fire-and-forget confirmation toast (§18: "brief confirmations after actions"). */
export function useToast() {
  const push = useContext(ToastContext);
  if (!push) throw new Error("useToast must be used within a ToastProvider");
  return push;
}
