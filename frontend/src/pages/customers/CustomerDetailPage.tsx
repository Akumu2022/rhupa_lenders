import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useParams } from "react-router-dom";
import { apiRequest, ApiError, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, EmptyState, Field, PageHeader, Select, SectionLabel, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { useAuth } from "../../auth/AuthContext";
import { kycStatusTone } from "../../schemas/compliance";
import type { ComplianceProfileResponse } from "../../schemas/compliance";
import {
  businessAssessmentSchema,
  refereeInputSchema,
  type BusinessAssessmentInput,
  type BusinessAssessmentResponse,
  type RefereeInputForm,
  type RefereeResponse,
} from "../../schemas/customers";
import type { LoanApplicationResponse, LoanProductResponse } from "../../schemas/loan";
import type { AdminLoanResponse } from "../../schemas/admin";
import { applicationHasPendingDecision, applicationStatusLabel, applicationStatusTone } from "../customer/shared";
import { LoanDetailDrawer, statusTone as loanStatusTone } from "../company/LoansPage";

function DetailRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-900 dark:text-slate-100">{value ?? "—"}</dd>
    </div>
  );
}

function BusinessAssessmentSection({ customerId, canManage }: { customerId: number; canManage: boolean }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const assessmentQuery = useQuery({
    queryKey: ["customers", customerId, "business-assessment"],
    queryFn: async () => {
      try {
        return await apiRequest<BusinessAssessmentResponse>(`/customers/${customerId}/business-assessment`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<BusinessAssessmentInput>({
    resolver: zodResolver(businessAssessmentSchema),
    values: assessmentQuery.data
      ? {
          business_name: assessmentQuery.data.business_name,
          business_type: assessmentQuery.data.business_type,
          ownership: assessmentQuery.data.ownership,
          physical_location: assessmentQuery.data.physical_location,
          years_in_operation: String(assessmentQuery.data.years_in_operation),
          sales_frequency: assessmentQuery.data.sales_frequency as "daily" | "weekly" | "monthly",
          total_income: assessmentQuery.data.total_income,
          total_expenses: assessmentQuery.data.total_expenses,
          reported_profit: assessmentQuery.data.reported_profit ?? undefined,
          stock_value: assessmentQuery.data.stock_value ?? undefined,
          existing_loans_amount: assessmentQuery.data.existing_loans_amount ?? undefined,
          other_lenders: assessmentQuery.data.other_lenders ?? undefined,
          bank_mpesa_turnover: assessmentQuery.data.bank_mpesa_turnover ?? undefined,
          business_assets_value: assessmentQuery.data.business_assets_value ?? undefined,
          cash_flow_notes: assessmentQuery.data.cash_flow_notes ?? undefined,
          existing_debt_obligations: assessmentQuery.data.existing_debt_obligations,
        }
      : undefined,
  });

  async function onSubmit(values: BusinessAssessmentInput) {
    setServerError(null);
    try {
      await apiRequest(`/customers/${customerId}/business-assessment`, { method: "PATCH", body: values });
      void queryClient.invalidateQueries({ queryKey: ["customers", customerId, "business-assessment"] });
      toast("Business assessment saved.", "success");
      setEditing(false);
    } catch (err) {
      setServerError(getErrorMessage(err));
    }
  }

  if (assessmentQuery.isLoading) return <Card>Loading…</Card>;

  if (!editing && !assessmentQuery.data) {
    return (
      <Card>
        <div className="flex items-center justify-between">
          <SectionLabel>Business assessment</SectionLabel>
          {canManage ? (
            <Button
              onClick={() => {
                reset({ sales_frequency: "monthly", existing_debt_obligations: "0" });
                setEditing(true);
              }}
            >
              Add assessment
            </Button>
          ) : null}
        </div>
        <EmptyState>No business assessment captured yet.</EmptyState>
      </Card>
    );
  }

  if (!editing && assessmentQuery.data) {
    const a = assessmentQuery.data;
    return (
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <SectionLabel>Business assessment</SectionLabel>
          {canManage ? (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Edit
            </Button>
          ) : null}
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <DetailRow label="Business name" value={a.business_name} />
          <DetailRow label="Type" value={a.business_type} />
          <DetailRow label="Ownership" value={a.ownership} />
          <DetailRow label="Location" value={a.physical_location} />
          <DetailRow label="Years in operation" value={a.years_in_operation} />
          <DetailRow label={`Income (${a.sales_frequency})`} value={`KES ${a.total_income}`} />
          <DetailRow label="Total expenses" value={`KES ${a.total_expenses}`} />
          <DetailRow label="Reported profit" value={a.reported_profit ? `KES ${a.reported_profit}` : null} />
          <DetailRow label="Existing debt obligations" value={`KES ${a.existing_debt_obligations}`} />
        </dl>
        <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/60">
          <DetailRow label="Net income (computed)" value={`KES ${a.net_income}`} />
          <DetailRow label="Debt service capacity (computed)" value={`KES ${a.debt_service_capacity}`} />
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <SectionLabel>{assessmentQuery.data ? "Edit business assessment" : "Add business assessment"}</SectionLabel>
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Business name" error={errors.business_name?.message}>
            <TextInput {...register("business_name")} />
          </Field>
          <Field label="Business type" error={errors.business_type?.message}>
            <TextInput {...register("business_type")} />
          </Field>
          <Field label="Ownership" error={errors.ownership?.message}>
            <TextInput {...register("ownership")} />
          </Field>
          <Field label="Physical location" error={errors.physical_location?.message}>
            <TextInput {...register("physical_location")} />
          </Field>
          <Field label="Years in operation" error={errors.years_in_operation?.message}>
            <TextInput type="number" min="0" step="1" {...register("years_in_operation")} />
          </Field>
          <Field label="Sales frequency" error={errors.sales_frequency?.message}>
            <Select {...register("sales_frequency")}>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </Select>
          </Field>
          <Field label="Total income for that period (KES)" error={errors.total_income?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("total_income")} />
          </Field>
          <Field label="Total expenses (KES)" error={errors.total_expenses?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("total_expenses")} />
          </Field>
          <Field label="Reported profit (optional)" error={errors.reported_profit?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("reported_profit")} />
          </Field>
          <Field label="Stock value (optional)" error={errors.stock_value?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("stock_value")} />
          </Field>
          <Field label="Existing loans amount (optional)" error={errors.existing_loans_amount?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("existing_loans_amount")} />
          </Field>
          <Field label="Other lenders (optional)" error={errors.other_lenders?.message}>
            <TextInput {...register("other_lenders")} />
          </Field>
          <Field label="Bank / M-Pesa turnover (optional)" error={errors.bank_mpesa_turnover?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("bank_mpesa_turnover")} />
          </Field>
          <Field label="Business assets value (optional)" error={errors.business_assets_value?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("business_assets_value")} />
          </Field>
          <Field label="Existing debt obligations (KES)" error={errors.existing_debt_obligations?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("existing_debt_obligations")} />
          </Field>
        </div>
        <Field label="Cash-flow notes (optional)" error={errors.cash_flow_notes?.message}>
          <TextInput {...register("cash_flow_notes")} />
        </Field>
        {serverError ? <Banner kind="error">{serverError}</Banner> : null}
        <div className="flex gap-2">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save"}
          </Button>
          <Button type="button" variant="secondary" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

function RefereesSection({ customerId, canManage }: { customerId: number; canManage: boolean }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);

  const refereesQuery = useQuery({
    queryKey: ["customers", customerId, "referees"],
    queryFn: () => apiRequest<RefereeResponse[]>(`/customers/${customerId}/referees`),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<RefereeInputForm>({ resolver: zodResolver(refereeInputSchema) });

  async function onSubmit(values: RefereeInputForm) {
    try {
      await apiRequest(`/customers/${customerId}/referees`, { method: "POST", body: values });
      void queryClient.invalidateQueries({ queryKey: ["customers", customerId, "referees"] });
      toast("Referee added.", "success");
      reset();
      setAdding(false);
    } catch (err) {
      toast(getErrorMessage(err), "error");
    }
  }

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <SectionLabel>Referees</SectionLabel>
        {canManage && !adding ? (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            Add referee
          </Button>
        ) : null}
      </div>

      {refereesQuery.data && refereesQuery.data.length > 0 ? (
        <ul className="space-y-2 text-sm">
          {refereesQuery.data.map((r) => (
            <li key={r.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <p className="font-medium text-slate-900 dark:text-slate-100">{r.full_name}</p>
              <p className="text-slate-500 dark:text-slate-400">
                {r.phone_number}
                {r.relationship ? ` · ${r.relationship}` : ""}
              </p>
            </li>
          ))}
        </ul>
      ) : !adding ? (
        <EmptyState>No referees added yet.</EmptyState>
      ) : null}

      {adding ? (
        <form className="mt-3 space-y-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <Field label="Full name" error={errors.full_name?.message}>
            <TextInput {...register("full_name")} />
          </Field>
          <Field label="Phone number" error={errors.phone_number?.message}>
            <TextInput {...register("phone_number")} />
          </Field>
          <Field label="Relationship (optional)" error={errors.relationship?.message}>
            <TextInput {...register("relationship")} />
          </Field>
          <Field label="Address (optional)" error={errors.address?.message}>
            <TextInput {...register("address")} />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Adding…" : "Add"}
            </Button>
            <Button type="button" variant="secondary" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}
    </Card>
  );
}

/** CLAUDE.md §8: the credit officer prepares the application on the
 * customer's behalf — an assisted path alongside (not replacing) customer
 * self-service (frontend/src/pages/customer/ApplyPage.tsx), which this
 * mirrors: product dropdown + amount + the same upfront estimated-terms
 * preview (§19 borrower transparency), just posting to
 * POST /customers/{id}/applications instead of /applications. */
function ApplyForCustomerDrawer({
  customerId,
  open,
  onClose,
}: {
  customerId: number;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

  const productsQuery = useQuery({
    queryKey: ["loan-products"],
    queryFn: () => apiRequest<LoanProductResponse[]>("/loan-products"),
    enabled: open,
  });

  const submit = useMutation({
    mutationFn: () =>
      apiRequest<LoanApplicationResponse>(`/customers/${customerId}/applications`, {
        method: "POST",
        body: { loan_product_id: selectedProductId, amount_requested: amount },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["customers", customerId, "applications"] });
      toast("Application submitted.", "success");
      setAmount("");
      setSelectedProductId(null);
      setError(null);
      onClose();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const selectedProduct = (productsQuery.data ?? []).find((p) => p.id === selectedProductId);
  const requestedAmount = Number(amount);
  const preview =
    selectedProduct && requestedAmount > 0
      ? {
          rate: selectedProduct.interest_rate,
          interest: ((requestedAmount * Number(selectedProduct.interest_rate)) / 100).toFixed(2),
          total: (requestedAmount + (requestedAmount * Number(selectedProduct.interest_rate)) / 100).toFixed(2),
          termDays: selectedProduct.repayment_period_days,
        }
      : null;

  return (
    <Drawer open={open} onClose={onClose} title="Apply for a loan">
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
          <TextInput type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        {preview ? (
          <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-sm dark:bg-slate-800/60">
            <p className="font-medium text-slate-700 dark:text-slate-300">Estimated terms</p>
            <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600 dark:text-slate-400">
              <span>Interest ({preview.rate}%)</span>
              <span className="text-right font-medium">KES {preview.interest}</span>
              <span>Total repayable</span>
              <span className="text-right font-medium">KES {preview.total}</span>
              <span>Repayment due</span>
              <span className="text-right font-medium">in {preview.termDays} days</span>
            </div>
          </div>
        ) : null}
        {error ? <Banner kind="error">{error}</Banner> : null}
        <Button disabled={!selectedProductId || !amount || submit.isPending} onClick={() => submit.mutate()} className="w-full">
          {submit.isPending ? "Submitting…" : "Submit application"}
        </Button>
      </div>
    </Drawer>
  );
}

function ApplicationsSection({ customerId, canManage }: { customerId: number; canManage: boolean }) {
  const [applyOpen, setApplyOpen] = useState(false);

  const applicationsQuery = useQuery({
    queryKey: ["customers", customerId, "applications"],
    queryFn: () => apiRequest<LoanApplicationResponse[]>(`/customers/${customerId}/applications`),
  });
  const productsQuery = useQuery({
    queryKey: ["loan-products"],
    queryFn: () => apiRequest<LoanProductResponse[]>("/loan-products"),
  });
  const productById = new Map((productsQuery.data ?? []).map((p) => [p.id, p]));
  const hasPending = applicationsQuery.data ? applicationHasPendingDecision(applicationsQuery.data) : false;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <SectionLabel>Applications</SectionLabel>
        {canManage ? (
          <Button disabled={hasPending} onClick={() => setApplyOpen(true)}>
            Apply for a loan
          </Button>
        ) : null}
      </div>
      {canManage && hasPending ? (
        <Banner kind="info">This customer already has a pending application — it must be decided first.</Banner>
      ) : null}
      <DataTable
        columns={[
          { key: "product", header: "Product", accessor: (a: LoanApplicationResponse) => productById.get(a.loan_product_id)?.name ?? "Loan" },
          {
            key: "amount",
            header: "Amount",
            accessor: (a) => a.amount_requested,
            render: (a) => `KES ${a.amount_requested}`,
          },
          {
            key: "status",
            header: "Status",
            accessor: (a) => a.status,
            render: (a) => <Badge tone={applicationStatusTone(a.status)}>{applicationStatusLabel(a.status)}</Badge>,
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
        emptyMessage="No applications yet."
      />
      <ApplyForCustomerDrawer customerId={customerId} open={applyOpen} onClose={() => setApplyOpen(false)} />
    </Card>
  );
}

function LoansSection({ customerId, canOpenDetail }: { customerId: number; canOpenDetail: boolean }) {
  const [selectedLoanId, setSelectedLoanId] = useState<number | null>(null);
  const loansQuery = useQuery({
    queryKey: ["customers", customerId, "loans"],
    queryFn: () => apiRequest<AdminLoanResponse[]>(`/customers/${customerId}/loans`),
  });

  return (
    <Card>
      <SectionLabel>Loans</SectionLabel>
      <DataTable
        columns={[
          { key: "product", header: "Product", accessor: (l: AdminLoanResponse) => l.loan_product_name },
          {
            key: "principal",
            header: "Principal",
            accessor: (l) => Number(l.principal),
            render: (l) => `KES ${l.principal}`,
          },
          {
            key: "outstanding",
            header: "Outstanding",
            accessor: (l) => Number(l.outstanding_balance),
            render: (l) => `KES ${l.outstanding_balance}`,
          },
          {
            key: "status",
            header: "Status",
            accessor: (l) => l.status,
            render: (l) => <Badge tone={loanStatusTone(l.status)}>{l.status.replace(/_/g, " ")}</Badge>,
          },
          {
            key: "disbursed_at",
            header: "Disbursed",
            sortable: true,
            accessor: (l) => l.disbursed_at ?? "",
            render: (l) => (l.disbursed_at ? new Date(l.disbursed_at).toLocaleDateString() : "Not yet"),
          },
        ]}
        data={loansQuery.data}
        getRowId={(l) => l.id}
        isLoading={loansQuery.isLoading}
        isError={loansQuery.isError}
        emptyMessage="No loans yet."
        onRowClick={canOpenDetail ? (l) => setSelectedLoanId(l.id) : undefined}
      />
      {canOpenDetail ? <LoanDetailDrawer loanId={selectedLoanId} onClose={() => setSelectedLoanId(null)} /> : null}
    </Card>
  );
}

/**
 * Thin wrapper so navigating between two customers (only the `:customerId`
 * route param changes) fully remounts the detail view below — otherwise
 * React Router keeps this component instance alive across the param change,
 * and local UI state in the section components (e.g. "editing"/"adding"
 * toggles) would leak from one customer to the next.
 */
export function CustomerDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  return <CustomerDetailView key={customerId} customerId={customerId} />;
}

function CustomerDetailView({ customerId }: { customerId: string | undefined }) {
  const { auth } = useAuth();
  // CLAUDE.md §8: credit_officer prepares (edits referees/business
  // assessment, applies on the customer's behalf); branch_manager and
  // system_administrator get the same page read-only, for oversight.
  const canManage = auth?.role === "credit_officer";

  const id = Number(customerId);
  const isValidId = Number.isFinite(id);

  const customerQuery = useQuery({
    queryKey: ["customers", id],
    queryFn: () => apiRequest<ComplianceProfileResponse>(`/customers/${id}`),
    enabled: isValidId,
  });

  const profile = customerQuery.data;

  return (
    <AppShell>
      <PageHeader
        title={profile ? profile.customer_full_name : "Customer"}
        subtitle={profile?.customer_number ?? undefined}
      />

      {!isValidId ? <Banner kind="error">Customer not found.</Banner> : null}
      {isValidId && customerQuery.isLoading ? <Card>Loading…</Card> : null}
      {isValidId && customerQuery.isError ? <Banner kind="error">Could not load this customer.</Banner> : null}

      {profile ? (
        <div className="space-y-4">
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <SectionLabel>Identity &amp; contact</SectionLabel>
              <Badge tone={kycStatusTone(profile.kyc_status)}>{profile.kyc_status}</Badge>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <DetailRow
                label="Full name"
                value={[profile.first_name, profile.middle_name, profile.last_name].filter(Boolean).join(" ") || null}
              />
              <DetailRow label="ID / passport" value={profile.national_id_number} />
              <DetailRow label="Gender" value={profile.gender} />
              <DetailRow label="Nationality" value={profile.nationality} />
              <DetailRow label="Marital status" value={profile.marital_status} />
              <DetailRow label="Dependants" value={profile.dependants_count} />
              <DetailRow label="Phone" value={profile.phone_number} />
              <DetailRow label="Alternate phone" value={profile.phone_number_alt} />
              <div className="col-span-2">
                <DetailRow label="Address" value={profile.residential_address} />
              </div>
              <DetailRow label="Employment" value={profile.employment_status} />
              <DetailRow label="Occupation" value={profile.occupation} />
              <div className="col-span-2">
                <DetailRow label="Monthly income" value={`KES ${profile.monthly_income}`} />
              </div>
            </dl>
          </Card>

          <Card>
            <SectionLabel>Next of kin</SectionLabel>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <DetailRow label="Name" value={profile.next_of_kin_name} />
              <DetailRow label="Relationship" value={profile.next_of_kin_relationship} />
              <DetailRow label="Phone" value={profile.next_of_kin_phone} />
            </dl>
          </Card>

          <LoansSection customerId={id} canOpenDetail={auth?.role === "system_administrator"} />
          <ApplicationsSection customerId={id} canManage={canManage} />
          <RefereesSection customerId={id} canManage={canManage} />
          <BusinessAssessmentSection customerId={id} canManage={canManage} />

          <p className="text-xs text-slate-400 dark:text-slate-500">
            KYC document review and verify/reject happen from the{" "}
            <a href="/compliance/queue" className="text-indigo-600 hover:underline dark:text-indigo-400">
              KYC queue
            </a>
            .
          </p>
        </div>
      ) : null}
    </AppShell>
  );
}
