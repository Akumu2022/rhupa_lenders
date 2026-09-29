import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, PageHeader, UsageMeter } from "../../components/ui";
import { AmortizationTable } from "../../components/AmortizationTable";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import type { CustomerCreditSummaryResponse, CustomerLoanResponse } from "../../schemas/loan";
import { loanStatusTone } from "./shared";

function ScheduleDrawer({ loan, onClose }: { loan: CustomerLoanResponse | null; onClose: () => void }) {
  return (
    <Drawer open={loan !== null} onClose={onClose} title={loan ? `${loan.loan_product_name} — schedule` : ""}>
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
              <p className="text-slate-500 dark:text-slate-400">Status</p>
              <Badge tone={loanStatusTone(loan.status)}>{loan.status}</Badge>
            </div>
          </div>
          <UsageMeter
            label="Repaid so far"
            used={Number(loan.total_repayable) - Number(loan.outstanding_balance)}
            total={Number(loan.total_repayable)}
            formatValue={(v) => `KES ${v.toLocaleString()}`}
          />
          <AmortizationTable schedule={loan.schedule} />
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Principal is the amount borrowed; interest is the lender's fee for the loan term — together they make up
            the amount due for each installment.
          </p>
        </div>
      ) : null}
    </Drawer>
  );
}

export function CustomerLoansPage() {
  const [selectedLoan, setSelectedLoan] = useState<CustomerLoanResponse | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["loans", "me"],
    queryFn: () => apiRequest<CustomerCreditSummaryResponse>("/loans/me"),
  });

  return (
    <AppShell>
      <PageHeader title="My loans" subtitle="Every loan you've had, past and present" />

      <Card>
        {summaryQuery.isError ? <Banner kind="error">Could not load your loans</Banner> : null}
        <DataTable
          columns={[
            { key: "product", header: "Product", accessor: (l: CustomerLoanResponse) => l.loan_product_name },
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
              render: (l) => <Badge tone={loanStatusTone(l.status)}>{l.status}</Badge>,
            },
            {
              key: "created_at",
              header: "Opened",
              sortable: true,
              accessor: (l) => l.created_at,
              render: (l) => new Date(l.created_at).toLocaleDateString(),
            },
          ]}
          data={summaryQuery.data?.loans}
          getRowId={(l) => l.id}
          isLoading={summaryQuery.isLoading}
          emptyMessage="You don't have any loans yet — apply from the Apply page."
          rowActions={(l) => (
            <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setSelectedLoan(l)}>
              View schedule
            </Button>
          )}
        />
      </Card>

      <ScheduleDrawer loan={selectedLoan} onClose={() => setSelectedLoan(null)} />
    </AppShell>
  );
}
