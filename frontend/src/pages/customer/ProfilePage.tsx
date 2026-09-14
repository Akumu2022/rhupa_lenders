import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, ApiError } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Card, LoadingRow, PageHeader, SectionLabel } from "../../components/ui";
import type { ProfileResponse } from "../../schemas/profile";
import { KycSubmitForm } from "./shared";

function kycTone(status: ProfileResponse["kyc_status"]): "success" | "warning" | "danger" {
  if (status === "verified") return "success";
  if (status === "rejected") return "danger";
  return "warning";
}

export function CustomerProfilePage() {
  const queryClient = useQueryClient();

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

  function handleSubmitted() {
    void queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
  }

  const profile = profileQuery.data ?? null;

  return (
    <AppShell>
      <PageHeader title="Profile" subtitle="Your identity verification and personal details" />

      {profileQuery.isLoading ? <LoadingRow /> : null}
      {profileQuery.isError ? <Banner kind="error">Could not load your profile</Banner> : null}

      {!profileQuery.isLoading && profile === null ? <KycSubmitForm onSubmitted={handleSubmitted} /> : null}

      {profile && profile.kyc_status === "rejected" ? (
        <KycSubmitForm onSubmitted={handleSubmitted} rejectionReason={profile.review_notes} />
      ) : null}

      {profile && profile.kyc_status === "verified" ? (
        <div className="mb-4">
          <Banner kind="success">Your identity has been verified — you can now apply for a loan.</Banner>
        </div>
      ) : null}

      {profile && profile.kyc_status !== "rejected" ? (
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <SectionLabel>Submitted details</SectionLabel>
            <Badge tone={kycTone(profile.kyc_status)}>{profile.kyc_status}</Badge>
          </div>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Date of birth</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.date_of_birth}</dd>
            </div>
            <div>
              <dt className="text-slate-500 dark:text-slate-400">National ID</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.national_id_number}</dd>
            </div>
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Phone number</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.phone_number}</dd>
            </div>
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Occupation</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.occupation}</dd>
            </div>
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Employment status</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.employment_status}</dd>
            </div>
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Monthly income</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">KES {profile.monthly_income}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-slate-500 dark:text-slate-400">Residential address</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.residential_address}</dd>
            </div>
          </dl>
          {profile.kyc_status === "pending" ? (
            <div className="mt-4">
              <Banner kind="info">Your identity verification is pending review.</Banner>
            </div>
          ) : null}
        </Card>
      ) : null}
    </AppShell>
  );
}
