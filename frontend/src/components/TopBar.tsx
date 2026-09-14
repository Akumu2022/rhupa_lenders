import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { apiRequest } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { CompanyInfoResponse } from "../schemas/company";
import { Badge } from "./ui";
import { Icon } from "./icons";
import { ROLE_HOME } from "./nav";
import { ThemeToggle } from "./ThemeToggle";

function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300"
        aria-label="Notifications"
      >
        <Icon name="bell" className="h-5 w-5" />
      </button>
      {open ? (
        <div className="absolute right-0 z-20 mt-2 w-64 rounded-lg border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-800">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
            Notifications
          </p>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            You're all caught up — no new notifications.
          </p>
        </div>
      ) : null}
    </div>
  );
}

export function TopBar({ title, onOpenMobileMenu }: { title: string; onOpenMobileMenu: () => void }) {
  const { auth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const companyQuery = useQuery({
    queryKey: ["companies", "me"],
    queryFn: () => apiRequest<CompanyInfoResponse>("/companies/me"),
    enabled: auth?.role !== "super_admin",
    retry: false,
  });

  // A real, always-available back affordance (not just relying on the
  // browser chrome) — hidden on each role's own dashboard root, since
  // there's nowhere further back to go within the app.
  const homePath = auth ? ROLE_HOME[auth.role] : undefined;
  const showBack = Boolean(homePath) && location.pathname !== homePath;

  return (
    <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-white/85 px-4 py-3 backdrop-blur dark:border-slate-800/70 dark:bg-slate-900/85">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            onClick={onOpenMobileMenu}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Open menu"
          >
            <Icon name="menu" className="h-5 w-5" />
          </button>
          {showBack ? (
            <button
              onClick={() => {
                // A direct deep-link (shared link, refresh, new tab) has no
                // in-app history to pop — `navigate(-1)` would then leave the
                // app entirely instead of "going back". React Router's
                // history entry index tells the two cases apart.
                const idx = (window.history.state as { idx?: number } | null)?.idx;
                if (typeof idx === "number" && idx > 0) navigate(-1);
                else if (homePath) navigate(homePath);
              }}
              className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              aria-label="Go back"
              title="Go back"
            >
              <Icon name="arrowLeft" className="h-4 w-4" />
            </button>
          ) : null}
          <h1 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h1>
        </div>
        <div className="flex items-center gap-2">
          {companyQuery.data ? (
            <span className="flex items-center gap-1.5">
              {companyQuery.data.logo_url ? (
                <img src={companyQuery.data.logo_url} alt="" className="h-5 w-5 rounded object-cover" />
              ) : null}
              <Badge
                tone={companyQuery.data.status === "active" ? "brand" : "danger"}
                // CLAUDE.md §21: cosmetic only — a bad/missing color never
                // breaks the badge, it just falls back to the platform's
                // default "brand" tone styling.
                style={
                  companyQuery.data.status === "active" && companyQuery.data.brand_primary_color
                    ? { backgroundColor: `${companyQuery.data.brand_primary_color}1a`, color: companyQuery.data.brand_primary_color }
                    : undefined
                }
              >
                {companyQuery.data.name}
                {companyQuery.data.status === "suspended" ? " · Suspended" : ""}
              </Badge>
            </span>
          ) : null}
          <ThemeToggle />
          <NotificationsBell />
        </div>
      </div>
    </header>
  );
}
