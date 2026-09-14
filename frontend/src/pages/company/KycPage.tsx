import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, PageHeader, Select, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { kycStatusTone } from "../../schemas/compliance";
import type { ComplianceProfileResponse } from "../../schemas/compliance";

function OverrideDrawer({ profile, onClose }: { profile: ComplianceProfileResponse | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [newStatus, setNewStatus] = useState<"verified" | "rejected">("verified");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (profile) {
      setNewStatus(profile.kyc_status === "verified" ? "rejected" : "verified");
      setReason("");
      setError(null);
    }
  }, [profile]);

  const override = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/kyc/${profile!.id}/override`, {
        method: "POST",
        body: { new_status: newStatus, reason },
      }),
    onSuccess: () => {
      // Same underlying Profile row is also read under ["compliance","history"]
      // (credit officer's KYC queue) and ["customers", id] (customer detail) —
      // invalidate all three, not just this page's own query.
      void queryClient.invalidateQueries({ queryKey: ["admin", "kyc"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "audit-log"] });
      void queryClient.invalidateQueries({ queryKey: ["compliance", "history"] });
      void queryClient.invalidateQueries({ queryKey: ["customers"] });
      toast(`${profile!.customer_full_name}'s KYC decision was overridden.`, "success");
      setReason("");
      onClose();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Drawer open={profile !== null} onClose={onClose} title={profile ? `Override — ${profile.customer_full_name}` : ""}>
      {profile ? (
        <div className="space-y-4">
          <Banner kind="info">
            This is an exceptional action, separate from the normal compliance review. It's logged distinctly and
            requires a reason.
          </Banner>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Current status: <Badge tone={kycStatusTone(profile.kyc_status)}>{profile.kyc_status}</Badge>
          </p>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
            Change to
            <Select className="mt-1.5" value={newStatus} onChange={(e) => setNewStatus(e.target.value as "verified" | "rejected")}>
              <option value="verified">Verified</option>
              <option value="rejected">Rejected</option>
            </Select>
          </label>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
            Reason (required)
            <TextInput className="mt-1.5" placeholder="Why is this override necessary?" value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          {error ? <Banner kind="error">{error}</Banner> : null}
          <Button
            variant="danger"
            className="w-full"
            disabled={!reason.trim() || newStatus === profile.kyc_status || override.isPending}
            onClick={() => override.mutate()}
          >
            {override.isPending ? "Overriding…" : "Override decision"}
          </Button>
        </div>
      ) : null}
    </Drawer>
  );
}

export function CompanyKycPage() {
  const [overriding, setOverriding] = useState<ComplianceProfileResponse | null>(null);

  const profilesQuery = useQuery({
    queryKey: ["admin", "kyc"],
    queryFn: () => apiRequest<ComplianceProfileResponse[]>("/admin/kyc"),
  });

  return (
    <AppShell>
      <PageHeader title="KYC" subtitle="Every identity submission in your company, any status" />

      <Card>
        <DataTable
          columns={[
            {
              key: "customer_number",
              header: "Customer #",
              accessor: (p: ComplianceProfileResponse) => p.customer_number ?? "—",
              render: (p) => <span className="font-mono text-xs">{p.customer_number ?? "—"}</span>,
            },
            { key: "customer", header: "Customer", sortable: true, accessor: (p) => p.customer_full_name },
            { key: "email", header: "Email", accessor: (p) => p.customer_email },
            { key: "national_id", header: "National ID", accessor: (p) => p.national_id_number },
            {
              key: "status",
              header: "Status",
              accessor: (p) => p.kyc_status,
              render: (p) => <Badge tone={kycStatusTone(p.kyc_status)}>{p.kyc_status}</Badge>,
            },
            {
              key: "created_at",
              header: "Submitted",
              sortable: true,
              accessor: (p) => p.created_at,
              render: (p) => new Date(p.created_at).toLocaleString(),
            },
          ]}
          data={profilesQuery.data}
          getRowId={(p) => p.id}
          isLoading={profilesQuery.isLoading}
          isError={profilesQuery.isError}
          searchKeys={["customer", "email", "national_id"]}
          searchPlaceholder="Search by name, email, or national ID…"
          emptyMessage="No KYC submissions yet."
          rowActions={(p) =>
            p.kyc_status === "pending" ? (
              <span className="text-xs text-slate-400 dark:text-slate-500">Awaiting review</span>
            ) : (
              <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setOverriding(p)}>
                Override
              </Button>
            )
          }
        />
      </Card>

      <OverrideDrawer profile={overriding} onClose={() => setOverriding(null)} />
    </AppShell>
  );
}
