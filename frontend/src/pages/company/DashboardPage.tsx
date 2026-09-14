import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import type { IconName } from "../../components/icons";
import {
  BarList,
  Card,
  EmptyState,
  HeroStat,
  HeroStatSkeleton,
  LinkTile,
  PageHeader,
  SectionLabel,
  Sparkline,
  StatCard,
  StatCardSkeleton,
} from "../../components/ui";
import type { UserResponse } from "../../schemas/staff";
import type { AuditLogResponse, PortfolioSummaryResponse, PortfolioTrendResponse } from "../../schemas/admin";

const QUICK_LINKS: { label: string; path: string; description: string; icon: IconName }[] = [
  { label: "Users", path: "/admin/users", description: "Add and manage compliance and credit officers", icon: "users" },
  { label: "Applications", path: "/admin/applications", description: "Every loan application, any status", icon: "documentText" },
  { label: "KYC", path: "/admin/kyc", description: "Every identity submission, any status", icon: "checkCircle" },
  { label: "Loans", path: "/admin/loans", description: "Every loan, past and present", icon: "banknotes" },
  { label: "Collections", path: "/admin/collections", description: "Overdue loans awaiting follow-up", icon: "archiveBox" },
  { label: "Products", path: "/admin/products", description: "Amount ranges, interest rates, active status", icon: "cube" },
  { label: "Portfolio", path: "/admin/portfolio", description: "Aggregate performance figures", icon: "chartBar" },
  { label: "Audit Log", path: "/admin/audit-log", description: "Every privileged action, append-only", icon: "clipboardList" },
  { label: "Company Profile", path: "/admin/company-profile", description: "Contacts, address, logo, brand colors", icon: "buildingOffice" },
];

function formatAction(action: string): string {
  return action.replace(/[._]/g, " ");
}

export function CompanyAdminDashboardPage() {
  const staffQuery = useQuery({
    queryKey: ["staff"],
    queryFn: () => apiRequest<UserResponse[]>("/staff"),
  });
  const portfolioQuery = useQuery({
    queryKey: ["admin", "portfolio", "summary"],
    queryFn: () => apiRequest<PortfolioSummaryResponse>("/admin/portfolio/summary"),
  });
  const trendQuery = useQuery({
    queryKey: ["admin", "portfolio", "trend"],
    queryFn: () => apiRequest<PortfolioTrendResponse>("/admin/portfolio/trend"),
  });
  const auditQuery = useQuery({
    queryKey: ["admin", "audit-log"],
    queryFn: () => apiRequest<AuditLogResponse[]>("/admin/audit-log"),
  });

  const activeCount = staffQuery.data?.filter((s) => s.is_active).length ?? null;
  const par = portfolioQuery.data ? Number(portfolioQuery.data.par_percentage) : null;
  const sparklineData = trendQuery.data?.points.map((p) => Number(p.disbursed_amount)) ?? [];
  const disbursedTotal = sparklineData.reduce((a, b) => a + b, 0);
  const recentActivity = auditQuery.data?.slice(0, 5) ?? [];
  const heroLoading = portfolioQuery.isLoading;

  const staffByRole = Object.entries(
    (staffQuery.data ?? []).reduce<Record<string, number>>((counts, staff) => {
      counts[staff.role] = (counts[staff.role] ?? 0) + 1;
      return counts;
    }, {}),
  ).map(([role, count]) => ({ label: role.replace(/_/g, " "), value: count, tone: "brand" as const }));

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Your company at a glance" />

      {/* §20: one verdict, top-left, largest type — everything else supports it. */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-5">
          {heroLoading ? (
            <HeroStatSkeleton />
          ) : portfolioQuery.isError ? (
            <div className="flex h-full items-center">
              <EmptyState>Could not load portfolio data. Try refreshing.</EmptyState>
            </div>
          ) : (
            <HeroStat
              label="Portfolio at risk"
              value={par !== null ? `${par}%` : "—"}
              tone={par !== null && par > 0 ? "danger" : "success"}
              subtext={
                portfolioQuery.data
                  ? `${portfolioQuery.data.overdue_loans} overdue · ${portfolioQuery.data.defaulted_loans} defaulted`
                  : undefined
              }
            />
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:col-span-7">
          {heroLoading ? (
            <>
              <StatCardSkeleton />
              <StatCardSkeleton />
              <StatCardSkeleton />
            </>
          ) : (
            <>
              <StatCard
                label="Outstanding principal"
                value={`KES ${portfolioQuery.data?.outstanding_principal ?? "—"}`}
                tone="neutral"
                icon="wallet"
              />
              <StatCard label="Active loans" value={portfolioQuery.data?.active_loans ?? "—"} tone="neutral" icon="documentText" />
              <StatCard label="Active staff" value={activeCount ?? "—"} tone="brand" icon="users" />
            </>
          )}
        </div>
      </div>

      <Card className="mt-4">
        <div className="flex items-center justify-between">
          <SectionLabel>Disbursement activity (last 14 days)</SectionLabel>
          {trendQuery.data ? (
            <span className="text-xs text-slate-400 dark:text-slate-500">KES {disbursedTotal.toLocaleString()} total</span>
          ) : null}
        </div>
        {trendQuery.isLoading ? (
          <div className="h-12 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
        ) : sparklineData.length > 1 ? (
          <Sparkline data={sparklineData} tone="brand" height={48} showArea formatValue={(v) => `KES ${v.toLocaleString()}`} />
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Not enough data yet.</p>
        )}
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <SectionLabel>Company management</SectionLabel>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {QUICK_LINKS.map((link) => (
              <LinkTile key={link.path} to={link.path} icon={link.icon} label={link.label} description={link.description} />
            ))}
          </div>
        </div>

        <div className="lg:col-span-4">
          <Card>
            <div className="flex items-center justify-between">
              <SectionLabel>Recent activity</SectionLabel>
              <Link to="/admin/audit-log" className="text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300">
                View all
              </Link>
            </div>
            {recentActivity.length === 0 ? (
              <EmptyState>No privileged actions logged yet.</EmptyState>
            ) : (
              <ul className="space-y-3">
                {recentActivity.map((entry) => (
                  <li key={entry.id} className="text-sm">
                    <p className="font-medium capitalize text-slate-800 dark:text-slate-100">{formatAction(entry.action)}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {entry.actor_email} · {new Date(entry.created_at).toLocaleString()}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="mt-4">
            <SectionLabel>Staff by role</SectionLabel>
            {staffByRole.length === 0 ? (
              <EmptyState>No staff yet.</EmptyState>
            ) : (
              <BarList items={staffByRole} />
            )}
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
