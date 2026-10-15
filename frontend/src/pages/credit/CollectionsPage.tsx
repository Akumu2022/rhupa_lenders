import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, PageHeader, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { useToast } from "../../components/toast";
import { useAuth } from "../../auth/AuthContext";
import type {
  CollectionDueItemResponse,
  CollectionReceivedItemResponse,
  CollectionsQueueItemResponse,
  LoanResponse,
} from "../../schemas/credit";

type Tab = "overdue" | "due" | "received" | "bad_debt";

const TABS: { value: Tab; label: string }[] = [
  { value: "overdue", label: "Overdue" },
  { value: "due", label: "Due in 7 days" },
  { value: "received", label: "Received (30 days)" },
  { value: "bad_debt", label: "Defaulted / bad debt" },
];

const SUBTITLES: Record<Tab, string> = {
  overdue: "Loans past their repayment due date — a human decides if and when to mark one defaulted",
  due: "Unpaid instalments falling due today through the next 7 days",
  received: "Repayments received in the last 30 days",
  bad_debt: "Defaulted and written-off loans — any later payment still counts; clearing the balance restores eligibility for new loans",
};

function sameDay(iso: string) {
  // Date-only strings (YYYY-MM-DD) must not shift a day in negative-offset
  // browsers, so render them as written.
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString();
}

function DueTable() {
  const dueQuery = useQuery({
    queryKey: ["collections", "due"],
    queryFn: () => apiRequest<CollectionDueItemResponse[]>("/credit/collections/due?days=7"),
  });
  return (
    <DataTable
      columns={[
        { key: "customer", header: "Customer", sortable: true, accessor: (i: CollectionDueItemResponse) => i.customer_full_name },
        { key: "product", header: "Product", accessor: (i) => i.loan_product_name },
        { key: "installment", header: "Instalment", accessor: (i) => i.installment_number, render: (i) => `#${i.installment_number}` },
        {
          key: "due_date",
          header: "Due",
          sortable: true,
          accessor: (i) => i.due_date,
          render: (i) => <Badge tone="warning">{sameDay(i.due_date)}</Badge>,
        },
        {
          key: "remaining",
          header: "Still to collect",
          sortable: true,
          accessor: (i) => Number(i.amount_remaining),
          render: (i) => `KES ${i.amount_remaining}`,
        },
      ]}
      data={dueQuery.data}
      getRowId={(i) => i.schedule_id}
      isLoading={dueQuery.isLoading}
      isError={dueQuery.isError}
      searchKeys={["customer"]}
      searchPlaceholder="Search by customer…"
      emptyMessage="No instalments fall due in the next 7 days."
    />
  );
}

function ReceivedTable() {
  const receivedQuery = useQuery({
    queryKey: ["collections", "received"],
    queryFn: () => apiRequest<CollectionReceivedItemResponse[]>("/credit/collections/received"),
  });
  return (
    <DataTable
      columns={[
        {
          key: "received_at",
          header: "Received",
          sortable: true,
          accessor: (r: CollectionReceivedItemResponse) => r.received_at,
          render: (r) => new Date(r.received_at).toLocaleString(),
        },
        { key: "customer", header: "Customer", sortable: true, accessor: (r) => r.customer_full_name },
        {
          key: "amount",
          header: "Amount",
          sortable: true,
          accessor: (r) => Number(r.amount),
          render: (r) => <Badge tone="success">KES {r.amount}</Badge>,
        },
        { key: "method", header: "Method", accessor: (r) => (r.method ?? "—").replace(/_/g, " ") },
        {
          key: "receipt",
          header: "Receipt #",
          accessor: (r) => r.receipt_number ?? "—",
          render: (r) => <span className="font-mono text-xs">{r.receipt_number ?? "—"}</span>,
        },
      ]}
      data={receivedQuery.data}
      getRowId={(r) => r.id}
      isLoading={receivedQuery.isLoading}
      isError={receivedQuery.isError}
      searchKeys={["customer", "receipt"]}
      searchPlaceholder="Search by customer or receipt…"
      emptyMessage="No repayments received in the last 30 days."
    />
  );
}

function MarkDefaultedAction({ loan }: { loan: CollectionsQueueItemResponse }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const markDefaulted = useMutation({
    mutationFn: () =>
      apiRequest<LoanResponse>(`/credit/loans/${loan.id}/mark-defaulted`, {
        method: "POST",
        body: { reason },
      }),
    onSuccess: () => {
      setReason("");
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["collections"] });
      toast(`${loan.customer_full_name}'s loan marked defaulted.`, "success");
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (!open) {
    return (
      <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => setOpen(true)}>
        Mark defaulted
      </Button>
    );
  }

  return (
    <div className="flex items-center justify-end gap-2">
      <TextInput
        placeholder="Reason (required)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="w-44 py-1 text-xs"
      />
      <Button
        variant="danger"
        className="px-2 py-1 text-xs"
        disabled={!reason.trim() || markDefaulted.isPending}
        onClick={() => markDefaulted.mutate()}
      >
        Confirm
      </Button>
      {error ? <span className="text-xs text-rose-600 dark:text-rose-400">{error}</span> : null}
    </div>
  );
}

interface DefaultedLoanItem {
  id: number;
  customer_id: number;
  customer_full_name: string;
  loan_product_name: string;
  principal: string;
  outstanding_balance: string;
  status: "defaulted" | "written_off";
}

function WriteOffAction({ loan }: { loan: DefaultedLoanItem }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const writeOff = useMutation({
    mutationFn: () =>
      apiRequest<LoanResponse>(`/credit/loans/${loan.id}/write-off`, { method: "POST", body: { reason } }),
    onSuccess: () => {
      setReason("");
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["collections"] });
      toast(`${loan.customer_full_name}'s loan written off as bad debt.`, "success");
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (loan.status === "written_off") return <Badge tone="danger">Written off</Badge>;
  if (!open) {
    return (
      <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => setOpen(true)}>
        Write off
      </Button>
    );
  }
  return (
    <div className="flex items-center justify-end gap-2">
      <TextInput
        placeholder="Reason (required)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="w-44 py-1 text-xs"
      />
      <Button
        variant="danger"
        className="px-2 py-1 text-xs"
        disabled={!reason.trim() || writeOff.isPending}
        onClick={() => writeOff.mutate()}
      >
        Confirm
      </Button>
      {error ? <span className="text-xs text-rose-600 dark:text-rose-400">{error}</span> : null}
    </div>
  );
}

function BadDebtTable() {
  const { auth } = useAuth();
  const canWriteOff = auth?.role === "branch_manager" || auth?.role === "system_administrator";
  const query = useQuery({
    queryKey: ["collections", "bad-debt"],
    queryFn: () => apiRequest<DefaultedLoanItem[]>("/credit/loans/defaulted"),
  });

  return (
    <>
      {query.isError ? <Banner kind="error">Could not load defaulted loans</Banner> : null}
      <DataTable
        columns={[
          { key: "customer", header: "Customer", sortable: true, accessor: (l: DefaultedLoanItem) => l.customer_full_name },
          { key: "product", header: "Product", accessor: (l) => l.loan_product_name },
          {
            key: "outstanding",
            header: "Still owed",
            sortable: true,
            accessor: (l) => Number(l.outstanding_balance),
            render: (l) => `KES ${l.outstanding_balance}`,
          },
          {
            key: "status",
            header: "Status",
            accessor: (l) => l.status,
            render: (l) => <Badge tone="danger">{l.status === "written_off" ? "Written off" : "Defaulted"}</Badge>,
          },
        ]}
        data={query.data}
        getRowId={(l) => l.id}
        isLoading={query.isLoading}
        searchKeys={["customer"]}
        searchPlaceholder="Search by customer…"
        emptyMessage="No defaulted or written-off loans."
        rowActions={canWriteOff ? (l) => <WriteOffAction loan={l} /> : undefined}
      />
    </>
  );
}

function OverdueTable() {
  const collectionsQuery = useQuery({
    queryKey: ["collections"],
    queryFn: () => apiRequest<CollectionsQueueItemResponse[]>("/credit/loans/collections"),
  });

  return (
    <>
      {collectionsQuery.isError ? <Banner kind="error">Could not load the collections queue</Banner> : null}
      <DataTable
          columns={[
            {
              key: "customer",
              header: "Customer",
              sortable: true,
              accessor: (l: CollectionsQueueItemResponse) => l.customer_full_name,
            },
            { key: "product", header: "Product", accessor: (l) => l.loan_product_name },
            {
              key: "outstanding",
              header: "Outstanding",
              sortable: true,
              accessor: (l) => Number(l.outstanding_balance),
              render: (l) => `KES ${l.outstanding_balance}`,
            },
            {
              key: "days_overdue",
              header: "Days overdue",
              sortable: true,
              accessor: (l) => l.days_overdue,
              render: (l) => <Badge tone="danger">{l.days_overdue}d overdue</Badge>,
            },
            {
              key: "due_date",
              header: "Was due",
              accessor: (l) => l.earliest_overdue_due_date,
              render: (l) => new Date(l.earliest_overdue_due_date).toLocaleDateString(),
            },
          ]}
          data={collectionsQuery.data}
          getRowId={(l) => l.id}
          isLoading={collectionsQuery.isLoading}
          searchKeys={["customer"]}
          searchPlaceholder="Search by customer…"
          emptyMessage="No loans are currently overdue."
          rowActions={(l) => <MarkDefaultedAction loan={l} />}
        />
    </>
  );
}

export function CollectionsPage() {
  const [tab, setTab] = useState<Tab>("overdue");

  return (
    <AppShell>
      <PageHeader title="Collections" subtitle={SUBTITLES[tab]} />

      <div className="mb-4 flex gap-2" role="tablist">
        {TABS.map((t) => (
          <Button
            key={t.value}
            role="tab"
            aria-selected={tab === t.value}
            variant={tab === t.value ? "primary" : "secondary"}
            className="px-3 py-1.5 text-xs"
            onClick={() => setTab(t.value)}
          >
            {t.label}
          </Button>
        ))}
      </div>

      <Card>
        {tab === "overdue" ? <OverdueTable /> : tab === "due" ? <DueTable /> : tab === "bad_debt" ? <BadDebtTable /> : <ReceivedTable />}
      </Card>
    </AppShell>
  );
}
