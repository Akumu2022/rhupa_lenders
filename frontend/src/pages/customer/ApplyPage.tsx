import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest, ApiError, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, Field, PageHeader, SectionLabel, Select, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import type { LoanApplicationResponse, LoanProductResponse } from "../../schemas/loan";
import type { ProfileResponse } from "../../schemas/profile";
import { applicationStatusTone } from "./shared";

export function CustomerApplyPage() {
  const queryClient = useQueryClient();
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

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
  const isVerified = profileQuery.data?.kyc_status === "verified";

  const productsQuery = useQuery({
    queryKey: ["loan-products"],
    queryFn: () => apiRequest<LoanProductResponse[]>("/loan-products"),
  });
  const applicationsQuery = useQuery({
    queryKey: ["applications", "me"],
    queryFn: () => apiRequest<LoanApplicationResponse[]>("/applications/me"),
  });

  const submit = useMutation({
    mutationFn: () =>
      apiRequest("/applications", {
        method: "POST",
        body: { loan_product_id: selectedProductId, amount_requested: amount },
      }),
    onSuccess: () => {
      setAmount("");
      setSelectedProductId(null);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["applications", "me"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const productById = new Map((productsQuery.data ?? []).map((p) => [p.id, p]));
  const hasPending = applicationsQuery.data?.some((a) => a.status === "pending") ?? false;

  const selectedProduct = selectedProductId ? productById.get(selectedProductId) : undefined;
  const requestedAmount = Number(amount);
  const selectedTermsPreview =
    selectedProduct && requestedAmount > 0
      ? {
          rate: selectedProduct.interest_rate,
          interest: ((requestedAmount * Number(selectedProduct.interest_rate)) / 100).toFixed(2),
          total: (requestedAmount + (requestedAmount * Number(selectedProduct.interest_rate)) / 100).toFixed(2),
          termDays: selectedProduct.repayment_period_days,
        }
      : null;

  return (
    <AppShell>
      <PageHeader title="Apply for a loan" subtitle="Choose a product and amount within its range" />

      {!profileQuery.isLoading && !isVerified ? (
        <Banner kind="info">
          Your identity must be verified before you can apply.{" "}
          <Link to="/customer/profile" className="font-medium underline">
            Go to your profile
          </Link>
          .
        </Banner>
      ) : null}

      {isVerified ? (
        <div className="space-y-4">
          {hasPending ? (
            <Banner kind="info">You have a pending loan application. You can apply again once it's decided.</Banner>
          ) : (
            <Card>
              <SectionLabel>New application</SectionLabel>
              <div className="space-y-4">
                <Field label="Loan product">
                  <Select
                    value={selectedProductId ?? ""}
                    onChange={(e) => setSelectedProductId(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Select a product…</option>
                    {productsQuery.data?.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name} (KES {product.min_amount}–{product.max_amount}, {product.interest_rate}%)
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Amount requested (KES)">
                  <TextInput
                    type="number"
                    step="0.01"
                    min="0"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                  />
                </Field>
                {selectedTermsPreview ? (
                  // CLAUDE.md §19 borrower transparency: the terms upfront,
                  // before submitting — never a surprise after approval.
                  <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-sm dark:bg-slate-800/60">
                    <p className="font-medium text-slate-700 dark:text-slate-300">Estimated terms</p>
                    <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600 dark:text-slate-400">
                      <span>Interest ({selectedTermsPreview.rate}%)</span>
                      <span className="text-right font-medium">KES {selectedTermsPreview.interest}</span>
                      <span>Total repayable</span>
                      <span className="text-right font-medium">KES {selectedTermsPreview.total}</span>
                      <span>Repayment due</span>
                      <span className="text-right font-medium">in {selectedTermsPreview.termDays} days</span>
                    </div>
                  </div>
                ) : null}
                {error ? <Banner kind="error">{error}</Banner> : null}
                <Button disabled={!selectedProductId || !amount || submit.isPending} onClick={() => submit.mutate()}>
                  {submit.isPending ? "Submitting…" : "Submit application"}
                </Button>
              </div>
            </Card>
          )}
        </div>
      ) : null}

      <Card className="mt-4">
        <SectionLabel>Your applications</SectionLabel>
        <DataTable
          columns={[
            {
              key: "product",
              header: "Product",
              accessor: (a) => productById.get(a.loan_product_id)?.name ?? "Loan",
            },
            { key: "amount", header: "Amount", accessor: (a) => a.amount_requested, render: (a) => `KES ${a.amount_requested}` },
            {
              key: "status",
              header: "Status",
              accessor: (a) => a.status,
              render: (a) => (
                <div>
                  <Badge tone={applicationStatusTone(a.status)}>{a.status}</Badge>
                  {a.status === "rejected" && a.review_notes ? (
                    <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">Reason: {a.review_notes}</p>
                  ) : null}
                </div>
              ),
            },
            {
              key: "created_at",
              header: "Submitted",
              sortable: true,
              accessor: (a) => a.created_at,
              render: (a) => new Date(a.created_at).toLocaleDateString(),
            },
          ]}
          data={applicationsQuery.data}
          getRowId={(a) => a.id}
          isLoading={applicationsQuery.isLoading}
          isError={applicationsQuery.isError}
          emptyMessage="You haven't applied for a loan yet."
        />
      </Card>
    </AppShell>
  );
}
