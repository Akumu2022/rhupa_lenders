import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiRequest } from "../../api/client";
import { AmortizationTable } from "../../components/AmortizationTable";
import { AppShell } from "../../components/AppShell";
import { Badge, Button, Card, PageHeader, UsageMeter } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import type { AdminLoanDetailResponse, AdminLoanResponse } from "../../schemas/admin";

// Same mapping as pages/customer/shared.tsx::loanStatusTone — §18: one status
// badge color vocabulary everywhere, staff and customer views alike.
function statusTone(status: AdminLoanResponse["status"]): "success" | "info" | "warning" | "danger" {
  if (status === "repaid") return "success";
  if (status === "active") return "info";
  if (status === "overdue") return "warning";
  if (status === "defaulted") return "danger";
  return "warning";
}

function LoanDetailDrawer({ loanId, onClose }: { loanId: number | null; onClose: () => void }) {
  const detailQuery = useQuery({
    queryKey: ["admin", "loans", loanId],
    queryFn: () => apiRequest<AdminLoanDetailResponse>(`/admin/loans/${loanId}`),
    enabled: loanId !== null,
  });
  const loan = detailQuery.data;

  return (
    <Drawer open={loanId !== null} onClose={onClose} title={loan ? `${loan.customer_full_name} — ${loan.loan_product_name}` : ""}>
      {loan ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-slate-500 dark:text-slate-400">Principal</p>
              <p className="font-semibold text-slate-900 dark:text-slate-100">KES {loan.principal}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Total repayable</p>
              <p className="font-semibold text-slate-900 dark:text-slate-100">KES {loan.total_repayable}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Outstanding balance</p>
              <p className="font-semibold text-slate-900 dark:text-slate-100">KES {loan.outstanding_balance}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Penalties accrued</p>
              <p className="font-semibold text-slate-900 dark:text-slate-100">KES {loan.penalties_accrued}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Status</p>
              <Badge tone={statusTone(loan.status)}>{loan.status}</Badge>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Disbursed</p>
              <p className="text-slate-700 dark:text-slate-300">
                {loan.disbursed_at ? new Date(loan.disbursed_at).toLocaleDateString() : "Not yet"}
              </p>
            </div>
          </div>
          <UsageMeter
            label="Repaid so far"
            used={Number(loan.total_repayable) - Number(loan.outstanding_balance)}
            total={Number(loan.total_repayable)}
            formatValue={(v) => `KES ${v.toLocaleString()}`}
          />
          <AmortizationTable schedule={loan.schedule} />
        </div>
      ) : (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
      )}
    </Drawer>
  );
}

export function CompanyLoansPage() {
  const navigate = useNavigate();
  const [selectedLoanId, setSelectedLoanId] = useState<number | null>(null);

  const loansQuery = useQuery({
    queryKey: ["admin", "loans"],
    queryFn: () => apiRequest<AdminLoanResponse[]>("/admin/loans"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Loans"
        subtitle="Every loan in your company, past and present"
        actions={
          <Button variant="secondary" onClick={() => navigate("/admin/loans/calculator")}>
            Calculator
          </Button>
        }
      />

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", sortable: true, accessor: (l: AdminLoanResponse) => l.customer_full_name },
            { key: "product", header: "Product", accessor: (l) => l.loan_product_name },
            {
              key: "principal",
              header: "Principal",
              sortable: true,
              accessor: (l) => Number(l.principal),
              render: (l) => `KES ${l.principal}`,
            },
            {
              key: "outstanding",
              header: "Outstanding",
              sortable: true,
              accessor: (l) => Number(l.outstanding_balance),
              render: (l) => `KES ${l.outstanding_balance}`,
            },
            {
              key: "status",
              header: "Status",
              accessor: (l) => l.status,
              render: (l) => <Badge tone={statusTone(l.status)}>{l.status}</Badge>,
            },
            {
              key: "created_at",
              header: "Opened",
              sortable: true,
              accessor: (l) => l.created_at,
              render: (l) => new Date(l.created_at).toLocaleDateString(),
            },
          ]}
          data={loansQuery.data}
          getRowId={(l) => l.id}
          isLoading={loansQuery.isLoading}
          isError={loansQuery.isError}
          searchKeys={["customer"]}
          searchPlaceholder="Search by customer…"
          emptyMessage="No loans yet."
          onRowClick={(l) => setSelectedLoanId(l.id)}
          rowActions={() => <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">Details →</span>}
        />
      </Card>

      <LoanDetailDrawer loanId={selectedLoanId} onClose={() => setSelectedLoanId(null)} />
    </AppShell>
  );
}
