import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiRequest, ApiError } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Card, HeroStat, LinkTile, LoadingRow, PageHeader, SectionLabel, StatCard, UsageMeter } from "../../components/ui";
import type { CustomerCreditSummaryResponse } from "../../schemas/loan";
import type { ProfileResponse } from "../../schemas/profile";

export function CustomerDashboardPage() {
  const profileQuery = useQuery({
    queryKey: ["profile", "me"],
    queryFn: async () => {
      try {
        return await apiRequest<ProfileResponse>("/profile");
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });

  const summaryQuery = useQuery({
    queryKey: ["loans", "me"],
    queryFn: () => apiRequest<CustomerCreditSummaryResponse>("/loans/me"),
    enabled: profileQuery.data?.kyc_status === "verified",
  });

  const profile = profileQuery.data ?? null;

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Your loan limit, standing, and identity status at a glance" />

      {profileQuery.isLoading ? <LoadingRow /> : null}

      {!profileQuery.isLoading && profile === null ? (
        <Banner kind="info">
          You haven't submitted your identity documents yet.{" "}
          <Link to="/customer/profile" className="font-medium underline">
            Complete your profile
          </Link>{" "}
          to unlock loan applications.
        </Banner>
      ) : null}

      {profile?.kyc_status === "pending" ? (
        <Banner kind="info">Your identity verification is pending review.</Banner>
      ) : null}

      {profile?.kyc_status === "rejected" ? (
        <Banner kind="error">
          Your identity verification was rejected: "{profile.review_notes}".{" "}
          <Link to="/customer/profile" className="font-medium underline">
            Resubmit your details
          </Link>
          .
        </Banner>
      ) : null}

      {profile?.kyc_status === "verified" ? (
        <div className="space-y-4">
          <Banner kind="success">Your identity has been verified — you can apply for a loan anytime.</Banner>

          {summaryQuery.isLoading ? <LoadingRow /> : null}
          {summaryQuery.data ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <div className="lg:col-span-5">
                <HeroStat
                  label="Available credit"
                  value={`KES ${summaryQuery.data.available_credit}`}
                  tone="brand"
                  subtext={`of KES ${summaryQuery.data.loan_limit} limit`}
                />
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-7">
                <StatCard label="Loan limit" value={`KES ${summaryQuery.data.loan_limit}`} tone="neutral" />
                <StatCard
                  label="Standing"
                  tone={summaryQuery.data.standing === "good_standing" ? "success" : "danger"}
                  value={
                    <Badge tone={summaryQuery.data.standing === "good_standing" ? "success" : "danger"}>
                      {summaryQuery.data.standing === "good_standing" ? "Good standing" : "Attention needed"}
                    </Badge>
                  }
                />
              </div>
            </div>
          ) : null}

          {summaryQuery.data ? (
            <Card>
              <SectionLabel>Credit utilization</SectionLabel>
              <UsageMeter
                label="Used of your loan limit"
                used={Number(summaryQuery.data.loan_limit) - Number(summaryQuery.data.available_credit)}
                total={Number(summaryQuery.data.loan_limit)}
                formatValue={(v) => `KES ${v.toLocaleString()}`}
              />
            </Card>
          ) : null}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <LinkTile to="/customer/loans" icon="wallet" label="My Loans" description="Your active and past loans" />
            <LinkTile to="/customer/apply" icon="plusCircle" label="Apply" description="Apply for a new loan" />
            <LinkTile to="/customer/repayments" icon="creditCard" label="Repayments" description="Make a repayment against your schedule" />
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
