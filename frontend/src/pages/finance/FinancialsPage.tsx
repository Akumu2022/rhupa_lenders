import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Banner, Button, Card, EmptyState, Field, PageHeader, SectionLabel, Select, StatCard, TextInput } from "../../components/ui";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import {
  EXPENSE_CATEGORIES,
  EXPENSE_CATEGORY_LABELS,
  expenseCreateSchema,
  type ExpenseCreateInput,
  type FinancialsResponse,
} from "../../schemas/finance";

function LogExpenseDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ExpenseCreateInput>({ resolver: zodResolver(expenseCreateSchema), defaultValues: { category: "other" } });

  async function onSubmit(values: ExpenseCreateInput) {
    setError(null);
    try {
      await apiRequest("/finance/expenses", { method: "POST", body: values });
      void queryClient.invalidateQueries({ queryKey: ["finance", "financials"] });
      toast("Expense logged.", "success");
      reset({ category: "other" });
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Log an expense">
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field label="Category" error={errors.category?.message}>
          <Select {...register("category")}>
            {EXPENSE_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {EXPENSE_CATEGORY_LABELS[c]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Amount (KES)" error={errors.amount?.message}>
          <TextInput type="number" step="0.01" min="0" {...register("amount")} />
        </Field>
        <Field label="Description" error={errors.description?.message}>
          <TextInput placeholder="Optional" {...register("description")} />
        </Field>
        {error ? <Banner kind="error">{error}</Banner> : null}
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Logging…" : "Log expense"}
        </Button>
      </form>
    </Drawer>
  );
}

/** CLAUDE.md §30: derived read-only from Transaction (income) + ExpenseEntry
 * (expenses) — never a second ledger. */
export function FinanceFinancialsPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const financialsQuery = useQuery({
    queryKey: ["finance", "financials"],
    queryFn: () => apiRequest<FinancialsResponse>("/finance/financials"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Financials"
        subtitle={financialsQuery.data ? `Trailing 30 days, since ${financialsQuery.data.period_start}` : "Cashbook-style summary"}
        actions={<Button onClick={() => setDrawerOpen(true)}>Log expense</Button>}
      />

      {financialsQuery.data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Repayment income" value={`KES ${financialsQuery.data.total_repayment_income}`} tone="success" />
            <StatCard label="Penalty income" value={`KES ${financialsQuery.data.total_penalty_income}`} tone="neutral" />
            <StatCard label="Disbursed" value={`KES ${financialsQuery.data.total_disbursed}`} tone="brand" />
            <StatCard
              label="Net"
              value={`KES ${financialsQuery.data.net}`}
              tone={Number(financialsQuery.data.net) >= 0 ? "success" : "danger"}
            />
          </div>

          <Card>
            <div className="flex items-center justify-between">
              <SectionLabel>Recent expenses</SectionLabel>
              <span className="text-xs text-slate-400 dark:text-slate-500">
                Total: KES {financialsQuery.data.total_expenses}
              </span>
            </div>
            {financialsQuery.data.recent_expenses.length === 0 ? (
              <EmptyState>No expenses logged in the last 30 days.</EmptyState>
            ) : (
              <ul className="space-y-3">
                {financialsQuery.data.recent_expenses.map((e) => (
                  <li key={e.id} className="flex items-center justify-between gap-2 text-sm">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-800 dark:text-slate-100">
                        {EXPENSE_CATEGORY_LABELS[e.category] ?? e.category}
                        {e.description ? ` — ${e.description}` : ""}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {e.created_by_name} · {new Date(e.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <span className="shrink-0 font-semibold text-slate-900 dark:text-slate-100">KES {e.amount}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      ) : null}

      <LogExpenseDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </AppShell>
  );
}
