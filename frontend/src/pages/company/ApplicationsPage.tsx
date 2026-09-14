import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, PageHeader, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { describeApplicationLifecycle, type CreditApplicationResponse, type LoanApprovalResponse } from "../../schemas/credit";

function OverrideDrawer({
  application,
  onClose,
}: {
  application: CreditApplicationResponse | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const override = useMutation({
    mutationFn: () =>
      apiRequest<LoanApprovalResponse>(`/admin/applications/${application!.id}/override`, {
        method: "POST",
        body: { reason },
      }),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "applications"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "loans"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "audit-log"] });
      toast(
        `${application!.customer_full_name}'s application was reactivated — loan of KES ${result.loan.principal} created.`,
        "success",
      );
      setReason("");
      onClose();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Drawer open={application !== null} onClose={onClose} title={application ? `Override — ${application.customer_full_name}` : ""}>
      {application ? (
        <div className="space-y-4">
          <Banner kind="info">
            This reactivates a rejected application as if it had been approved — it creates a loan. This is an
            exceptional action, logged distinctly, separate from the normal credit review.
          </Banner>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {application.loan_product_name} — KES {application.amount_requested}
          </p>
          {application.review_notes ? (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Original rejection reason: "{application.review_notes}"
            </p>
          ) : null}
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
            Reason (required)
            <TextInput
              className="mt-1.5"
              placeholder="Why should this be reactivated?"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          {error ? <Banner kind="error">{error}</Banner> : null}
          <Button variant="danger" className="w-full" disabled={!reason.trim() || override.isPending} onClick={() => override.mutate()}>
            {override.isPending ? "Overriding…" : "Reactivate and approve"}
          </Button>
        </div>
      ) : null}
    </Drawer>
  );
}

export function CompanyApplicationsPage() {
  const [overriding, setOverriding] = useState<CreditApplicationResponse | null>(null);

  const applicationsQuery = useQuery({
    queryKey: ["admin", "applications"],
    queryFn: () => apiRequest<CreditApplicationResponse[]>("/admin/applications"),
  });

  return (
    <AppShell>
      <PageHeader title="Applications" subtitle="Every loan application in your company, any status" />

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", sortable: true, accessor: (a: CreditApplicationResponse) => a.customer_full_name },
            { key: "email", header: "Email", accessor: (a) => a.customer_email },
            { key: "product", header: "Product", accessor: (a) => a.loan_product_name },
            {
              key: "amount",
              header: "Amount",
              sortable: true,
              accessor: (a) => Number(a.amount_requested),
              render: (a) => `KES ${a.amount_requested}`,
            },
            {
              key: "status",
              header: "Status",
              accessor: (a) => a.status,
              render: (a) => {
                const { label, tone } = describeApplicationLifecycle(a);
                return <Badge tone={tone}>{label}</Badge>;
              },
            },
            {
              key: "created_at",
              header: "Submitted",
              sortable: true,
              accessor: (a) => a.created_at,
              render: (a) => new Date(a.created_at).toLocaleString(),
            },
          ]}
          data={applicationsQuery.data}
          getRowId={(a) => a.id}
          isLoading={applicationsQuery.isLoading}
          isError={applicationsQuery.isError}
          searchKeys={["customer", "email"]}
          searchPlaceholder="Search by customer or email…"
          emptyMessage="No applications yet."
          rowActions={(a) =>
            a.status === "rejected" ? (
              <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setOverriding(a)}>
                Override
              </Button>
            ) : null
          }
        />
      </Card>

      <OverrideDrawer application={overriding} onClose={() => setOverriding(null)} />
    </AppShell>
  );
}
