import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { apiRequest } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { BrandingContext, safeHex } from "../branding";
import type { CompanyInfoResponse } from "../schemas/company";
import { NAV_BY_ROLE } from "./nav";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { AuroraBackground } from "./ui";

const PLATFORM_TITLE = "Rupha Royals";

function currentPageTitle(role: string | undefined, pathname: string): string {
  const items = role ? (NAV_BY_ROLE[role] ?? []) : [];
  // Longest matching path wins (e.g. "/credit/applications" over "/credit").
  const match = [...items].sort((a, b) => b.path.length - a.path.length).find((item) => pathname.startsWith(item.path));
  return match?.label ?? "Dashboard";
}

export function AppShell({ children }: { children: ReactNode }) {
  const { auth } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // CLAUDE.md §21: resolve the logged-in staff/customer's OWN company once
  // here and hand it down via BrandingContext, so every shell surface reads
  // the same tenant identity instead of the platform's hardcoded name.
  // super_admin has no single company (§21: platform console stays neutral).
  const companyQuery = useQuery({
    queryKey: ["companies", "me"],
    queryFn: () => apiRequest<CompanyInfoResponse>("/companies/me"),
    enabled: auth?.role !== "super_admin",
    retry: false,
  });

  const branding = {
    name: companyQuery.data?.name,
    tagline: companyQuery.data?.tagline,
    logoUrl: companyQuery.data?.logo_url,
    primaryColor: companyQuery.data?.brand_primary_color,
    accentColor: companyQuery.data?.brand_accent_color,
  };

  useEffect(() => {
    document.title = branding.name ? `${branding.name} · ${PLATFORM_TITLE}` : PLATFORM_TITLE;
    return () => {
      document.title = PLATFORM_TITLE;
    };
  }, [branding.name]);

  // CSS custom properties alongside the React context: most brand accents
  // (sidebar mark, buttons, stat cards) read `useBranding()` directly, but a
  // few (hover states, e.g. LinkTile) can only be expressed in pure CSS —
  // this is the one place company_id resolves to colors, so it's the one
  // place that writes them (CLAUDE.md §21: "the platform controls the
  // MECHANISM"). Cleared on unmount/company change so a stale color never
  // survives a switch back to an unbranded company or to super_admin.
  useEffect(() => {
    const root = document.documentElement;
    const primary = safeHex(branding.primaryColor);
    const accent = safeHex(branding.accentColor);
    if (primary) root.style.setProperty("--brand-primary", primary);
    else root.style.removeProperty("--brand-primary");
    if (accent) root.style.setProperty("--brand-accent", accent);
    else root.style.removeProperty("--brand-accent");
    return () => {
      root.style.removeProperty("--brand-primary");
      root.style.removeProperty("--brand-accent");
    };
  }, [branding.primaryColor, branding.accentColor]);

  return (
    <BrandingContext.Provider value={branding}>
      <div className="flex min-h-screen bg-[#f6f5fb] dark:bg-[#0b0e14]">
        <Sidebar
          collapsed={collapsed}
          onToggleCollapsed={() => setCollapsed((v) => !v)}
          mobileOpen={mobileOpen}
          onCloseMobile={() => setMobileOpen(false)}
        />
        <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          <AuroraBackground />
          <TopBar title={currentPageTitle(auth?.role, location.pathname)} onOpenMobileMenu={() => setMobileOpen(true)} />
          <main key={location.pathname} className="animate-page-in relative mx-auto w-full max-w-5xl flex-1 px-4 py-8">
            {children}
          </main>
        </div>
      </div>
    </BrandingContext.Provider>
  );
}
