import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, PageHeader, SectionLabel, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import type { CustomerCreditSummaryResponse, CustomerLoanResponse, RepaymentResponse, TransactionResponse } from "../../schemas/loan";

function RepayDrawer({ loan, onClose }: { loan: CustomerLoanResponse | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

  const repay = useMutation({
    mutationFn: () =>
      apiRequest<RepaymentResponse>(`/loans/${loan!.id}/repay`, { method: "POST", body: { amount } }),
    onSuccess: (result) => {
      setError(null);
      setAmount("");
      void queryClient.invalidateQueries({ queryKey: ["loans", "me"] });
      void queryClient.invalidateQueries({ queryKey: ["transactions", "me"] });
      toast(
        result.status === "repaid" ? "Loan fully repaid." : `Payment of KES ${amount} recorded.`,
        "success",
      );
      onClose();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Drawer open={loan !== null} onClose={onClose} title={loan ? `Repay — ${loan.loan_product_name}` : ""}>
      {loan ? (
        <div className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Outstanding balance:{" "}
            <span className="font-semibold text-slate-900 dark:text-slate-100">KES {loan.outstanding_balance}</span>
          </p>
          <TextInput
            type="number"
            step="0.01"
            min="0"
            max={loan.outstanding_balance}
            placeholder="Amount to pay"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          {error ? <Banner kind="error">{error}</Banner> : null}
          <Button disabled={!amount || repay.isPending} onClick={() => repay.mutate()} className="w-full">
            {repay.isPending ? "Paying…" : "Confirm payment"}
          </Button>
        </div>
      ) : null}
    </Drawer>
  );
}

export function CustomerRepaymentsPage() {
  const [selectedLoan, setSelectedLoan] = useState<CustomerLoanResponse | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["loans", "me"],
    queryFn: () => apiRequest<CustomerCreditSummaryResponse>("/loans/me"),
  });
  const transactionsQuery = useQuery({
    queryKey: ["transactions", "me"],
    queryFn: () => apiRequest<TransactionResponse[]>("/transactions/me"),
  });

  const dueLoans = (summaryQuery.data?.loans ?? []).filter(
    (l) => l.status === "active" && Number(l.outstanding_balance) > 0,
  );

  return (
    <AppShell>
      <PageHeader title="Repayments" subtitle="Pay down your active loans and review past transactions" />

      <div className="space-y-4">
        <Card>
          <SectionLabel>Due for repayment</SectionLabel>
          <DataTable
            columns={[
              { key: "product", header: "Loan", accessor: (l: CustomerLoanResponse) => l.loan_product_name },
              {
                key: "outstanding",
                header: "Outstanding",
                sortable: true,
                accessor: (l) => Number(l.outstanding_balance),
                render: (l) => `KES ${l.outstanding_balance}`,
              },
              {
                key: "due",
                header: "Next due date",
                accessor: (l) => l.schedule.find((s) => !s.is_paid)?.due_date ?? "",
              },
            ]}
            data={dueLoans}
            getRowId={(l) => l.id}
            isLoading={summaryQuery.isLoading}
            emptyMessage="Nothing due — you have no active loans with a balance owing."
            rowActions={(l) => (
              <Button className="px-2 py-1 text-xs" onClick={() => setSelectedLoan(l)}>
                Repay now
              </Button>
            )}
          />
        </Card>

        <Card>
          <SectionLabel>Transaction history</SectionLabel>
          <DataTable
            columns={[
              {
                key: "type",
                header: "Type",
                accessor: (t: TransactionResponse) => t.type,
                render: (t) => (
                  <Badge tone={t.type === "disbursement" ? "info" : "success"} className="capitalize">
                    {t.type}
                  </Badge>
                ),
              },
              {
                key: "amount",
                header: "Amount",
                sortable: true,
                accessor: (t) => Number(t.amount),
                render: (t) => `KES ${t.amount}`,
              },
              {
                key: "created_at",
                header: "Date",
                sortable: true,
                accessor: (t) => t.created_at,
                render: (t) => new Date(t.created_at).toLocaleString(),
              },
            ]}
            data={transactionsQuery.data}
            getRowId={(t) => t.id}
            isLoading={transactionsQuery.isLoading}
            isError={transactionsQuery.isError}
            emptyMessage="No transactions yet."
          />
        </Card>
      </div>

      <RepayDrawer loan={selectedLoan} onClose={() => setSelectedLoan(null)} />
    </AppShell>
  );
}
