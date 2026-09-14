import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { safeHex, useBranding } from "../branding";
import { Icon } from "./icons";
import { NAV_BY_ROLE, ROLE_LABELS } from "./nav";

export function Sidebar({
  collapsed,
  onToggleCollapsed,
  mobileOpen,
  onCloseMobile,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const { auth, logout } = useAuth();
  const navigate = useNavigate();
  const branding = useBranding();
  if (!auth) return null;

  const items = NAV_BY_ROLE[auth.role] ?? [];

  // CLAUDE.md §21: "shows on the company's own surfaces... A Company-A user
  // sees Company-A identity throughout." super_admin (no `branding.name`,
  // §21: platform console stays neutral) and the moment before /companies/me
  // resolves both fall back to the platform's own identity.
  const brandName = branding.name ?? "Rupha Royals";
  const brandSubtitle = branding.tagline ?? "Lending Platform";
  const primary = safeHex(branding.primaryColor);
  const accent = safeHex(branding.accentColor);
  const markStyle = primary ? { backgroundImage: `linear-gradient(135deg, ${primary}, ${accent ?? primary})` } : undefined;

  const body = (
    <div className="flex h-full flex-col bg-white dark:bg-slate-900">
      <div className={`flex items-center gap-2.5 border-b border-slate-100 px-4 py-4 dark:border-slate-800 ${collapsed ? "justify-center px-2" : ""}`}>
        {branding.logoUrl ? (
          <img
            src={branding.logoUrl}
            alt=""
            className="h-8 w-8 shrink-0 rounded-lg object-cover shadow-sm"
          />
        ) : (
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 text-sm font-bold text-white shadow-sm shadow-indigo-600/30"
            style={markStyle}
          >
            {brandName.charAt(0).toUpperCase()}
          </span>
        )}
        {!collapsed ? (
          <div className="min-w-0 leading-tight">
            <p className="truncate text-sm font-bold tracking-tight text-slate-900 dark:text-slate-50">{brandName}</p>
            <p className="truncate text-[11px] font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
              {brandSubtitle}
            </p>
          </div>
        ) : null}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-4">
        {items.map((item) =>
          item.soon ? (
            <div
              key={item.path}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-300 dark:text-slate-600 ${collapsed ? "justify-center" : ""}`}
              title={collapsed ? `${item.label} — coming soon` : undefined}
            >
              <Icon name={item.icon} className="h-5 w-5 shrink-0" />
              {!collapsed ? (
                <>
                  <span className="flex-1">{item.label}</span>
                  <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                    Soon
                  </span>
                </>
              ) : null}
            </div>
          ) : (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === (NAV_BY_ROLE[auth.role]?.[0]?.path ?? "")}
              onClick={onCloseMobile}
              style={({ isActive }) =>
                isActive && primary ? { backgroundColor: `${primary}1a`, color: primary } : undefined
              }
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  collapsed ? "justify-center" : ""
                } ${
                  isActive
                    ? primary
                      ? ""
                      : "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                }`
              }
              title={collapsed ? item.label : undefined}
            >
              <Icon name={item.icon} className="h-5 w-5 shrink-0" />
              {!collapsed ? item.label : null}
            </NavLink>
          ),
        )}
      </nav>

      <div className="border-t border-slate-100 p-3 dark:border-slate-800">
        <button
          onClick={onToggleCollapsed}
          className={`mb-2 hidden w-full items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-50 hover:text-slate-600 lg:flex dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300 ${collapsed ? "justify-center" : ""}`}
        >
          <Icon name={collapsed ? "chevronsRight" : "chevronsLeft"} className="h-4 w-4" />
          {!collapsed ? "Collapse" : null}
        </button>
        <div className={`flex items-center gap-2.5 rounded-lg px-2 py-2 ${collapsed ? "justify-center" : ""}`}>
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {(ROLE_LABELS[auth.role] ?? auth.role).charAt(0)}
          </span>
          {!collapsed ? (
            <div className="min-w-0 flex-1 leading-tight">
              <p className="truncate text-xs font-semibold text-slate-700 dark:text-slate-300">
                {ROLE_LABELS[auth.role] ?? auth.role}
              </p>
              <button
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
                className="text-[11px] font-medium text-slate-400 hover:text-rose-600 dark:text-slate-500 dark:hover:text-rose-400"
              >
                Log out
              </button>
            </div>
          ) : null}
        </div>
        {collapsed ? (
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="mt-1 flex w-full items-center justify-center rounded-lg px-3 py-1.5 text-slate-400 hover:bg-slate-50 hover:text-rose-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-rose-400"
            title="Log out"
          >
            <Icon name="logout" className="h-4 w-4" />
          </button>
        ) : null}
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: part of the flex layout, width transitions on collapse */}
      <aside
        className={`sticky top-0 hidden h-screen shrink-0 border-r border-slate-200/80 transition-[width] duration-150 lg:block dark:border-slate-800 ${
          collapsed ? "w-[72px]" : "w-60"
        }`}
      >
        {body}
      </aside>

      {/* Mobile: overlay drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/30" onClick={onCloseMobile} />
          <aside className="absolute inset-y-0 left-0 w-64 shadow-2xl">{body}</aside>
        </div>
      ) : null}
    </>
  );
}
