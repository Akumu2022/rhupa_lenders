import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm, type FieldErrors, type UseFormRegister } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, Field, PageHeader, Select, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { useApiMutation } from "../../hooks/useApiMutation";
import {
  productCreateSchema,
  productUpdateSchema,
  type AdminLoanProductResponse,
  type ProductCreateInput,
  type ProductUpdateInput,
} from "../../schemas/admin";

/** Query params the loan calculator page (frontend/src/pages/company/LoanCalculatorPage.tsx)
 * reads to prefill itself from a specific product's own configured rate/term
 * — "the rates are set by admin here, so admin should be able to preview
 * exactly what they produce" without retyping them by hand. */
function calculatorUrlForProduct(product: AdminLoanProductResponse): string {
  const params = new URLSearchParams({
    principal: product.min_amount,
    interest_rate: product.interest_rate,
    interest_model: product.interest_model,
    term_days: String(product.repayment_period_days),
    installment_count: String(product.installment_count),
    product_name: product.name,
  });
  return `/admin/loans/calculator?${params.toString()}`;
}

const INTEREST_MODEL_LABELS: Record<string, string> = {
  flat: "Flat (principal × rate, once)",
  reducing_balance: "Reducing balance (amortized)",
  daily_accrual: "Daily accrual",
};

// ProductCreateInput and ProductUpdateInput are structurally identical (both
// z.infer the same shared field set, schemas/admin.ts) — this form is
// shared by the create and edit drawers.
function ProductFormFields({
  register,
  errors,
}: {
  register: UseFormRegister<ProductUpdateInput>;
  errors: FieldErrors<ProductUpdateInput>;
}) {
  return (
    <>
      <Field label="Product name" error={errors.name?.message}>
        <TextInput {...register("name")} />
      </Field>
      <Field label="Description" error={errors.description?.message}>
        <TextInput {...register("description")} />
      </Field>
      <Field label="Minimum amount (KES)" error={errors.min_amount?.message}>
        <TextInput type="number" step="0.01" min="0" {...register("min_amount")} />
      </Field>
      <Field label="Maximum amount (KES)" error={errors.max_amount?.message}>
        <TextInput type="number" step="0.01" min="0" {...register("max_amount")} />
      </Field>
      <Field label="Interest rate (%)" error={errors.interest_rate?.message}>
        <TextInput type="number" step="0.01" min="0" {...register("interest_rate")} />
      </Field>
      <Field label="Repayment period (days)" error={errors.repayment_period_days?.message}>
        <TextInput type="number" step="1" min="1" {...register("repayment_period_days")} />
      </Field>
      <Field label="Interest model" error={errors.interest_model?.message}>
        <Select {...register("interest_model")}>
          {Object.entries(INTEREST_MODEL_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Number of installments" error={errors.installment_count?.message}>
        <TextInput type="number" step="1" min="1" {...register("installment_count")} />
      </Field>
      <Field label="Penalty rate (% per day overdue)" error={errors.penalty_rate?.message}>
        <TextInput type="number" step="0.01" min="0" {...register("penalty_rate")} />
      </Field>
      <Field label="Grace period (days)" error={errors.grace_period_days?.message}>
        <TextInput type="number" step="1" min="0" {...register("grace_period_days")} />
      </Field>
      <Field label="Penalty cap (ratio of principal, e.g. 1.00 = 100%)" error={errors.penalty_cap_ratio?.message}>
        <TextInput type="number" step="0.01" min="0" {...register("penalty_cap_ratio")} />
      </Field>
      <Field label="Branch manager delegated limit (KES)" error={errors.branch_manager_delegated_limit?.message}>
        <TextInput type="number" step="0.01" min="0" {...register("branch_manager_delegated_limit")} />
      </Field>
      <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
        <input type="checkbox" className="h-4 w-4 rounded border-slate-300" {...register("requires_guarantor")} />
        Requires at least one verified guarantor before approval
      </label>
    </>
  );
}

function CreateProductDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProductCreateInput>({
    resolver: zodResolver(productCreateSchema),
    defaultValues: {
      interest_model: "flat",
      installment_count: "1",
      penalty_rate: "1.00",
      grace_period_days: "3",
      penalty_cap_ratio: "1.00",
      branch_manager_delegated_limit: "100000.00",
    },
  });

  async function onSubmit(values: ProductCreateInput) {
    setError(null);
    try {
      const product = await apiRequest<AdminLoanProductResponse>("/admin/products", {
        method: "POST",
        body: {
          ...values,
          repayment_period_days: Number(values.repayment_period_days),
          installment_count: Number(values.installment_count),
          grace_period_days: Number(values.grace_period_days),
        },
      });
      void queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      toast(`${product.name} created.`, "success");
      reset();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="New product">
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <ProductFormFields register={register} errors={errors} />
        {error ? <Banner kind="error">{error}</Banner> : null}
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Creating…" : "Create product"}
        </Button>
      </form>
    </Drawer>
  );
}

function EditProductDrawer({ product, onClose }: { product: AdminLoanProductResponse | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProductUpdateInput>({ resolver: zodResolver(productUpdateSchema) });

  useEffect(() => {
    if (product) {
      reset({
        name: product.name,
        description: product.description ?? "",
        min_amount: product.min_amount,
        max_amount: product.max_amount,
        interest_rate: product.interest_rate,
        repayment_period_days: String(product.repayment_period_days),
        interest_model: product.interest_model,
        installment_count: String(product.installment_count),
        penalty_rate: product.penalty_rate,
        grace_period_days: String(product.grace_period_days),
        penalty_cap_ratio: product.penalty_cap_ratio,
        branch_manager_delegated_limit: product.branch_manager_delegated_limit,
        requires_guarantor: product.requires_guarantor,
      });
    }
  }, [product, reset]);

  async function onSubmit(values: ProductUpdateInput) {
    if (!product) return;
    setError(null);
    try {
      await apiRequest(`/admin/products/${product.id}`, {
        method: "PATCH",
        body: {
          ...values,
          repayment_period_days: Number(values.repayment_period_days),
          installment_count: Number(values.installment_count),
          grace_period_days: Number(values.grace_period_days),
        },
      });
      void queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      toast(`${product.name} updated.`, "success");
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  const toggleActive = useMutation({
    mutationFn: () =>
      apiRequest<AdminLoanProductResponse>(`/admin/products/${product!.id}`, {
        method: "PATCH",
        body: { is_active: !product!.is_active },
      }),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      toast(`${updated.name} ${updated.is_active ? "activated" : "deactivated"}.`, "success");
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Drawer open={product !== null} onClose={onClose} title={product ? product.name : ""}>
      {product ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
            <span className="text-sm text-slate-600 dark:text-slate-400">
              Status: <Badge tone={product.is_active ? "success" : "neutral"}>{product.is_active ? "Active" : "Inactive"}</Badge>
            </span>
            <Button variant="secondary" className="px-2 py-1 text-xs" disabled={toggleActive.isPending} onClick={() => toggleActive.mutate()}>
              {product.is_active ? "Deactivate" : "Activate"}
            </Button>
          </div>

          <button
            type="button"
            onClick={() => navigate(calculatorUrlForProduct(product))}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            Preview this product's numbers in the calculator →
          </button>

          <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <ProductFormFields register={register} errors={errors} />
            {error ? <Banner kind="error">{error}</Banner> : null}
            <Button type="submit" disabled={isSubmitting} className="w-full">
              {isSubmitting ? "Saving…" : "Save changes"}
            </Button>
          </form>
        </div>
      ) : null}
    </Drawer>
  );
}

/** A real delete — succeeds only for a product no application/loan has ever
 * used (the backend enforces this; a used product gets a clear 409 telling
 * the admin to deactivate it instead, surfaced here via the default
 * toast-on-error behavior of useApiMutation). Two-step confirm since this is
 * irreversible, unlike Deactivate. */
function DeleteProductAction({ product }: { product: AdminLoanProductResponse }) {
  const [confirming, setConfirming] = useState(false);
  const deleteMutation = useApiMutation({
    mutationFn: () => apiRequest(`/admin/products/${product.id}`, { method: "DELETE" }),
    queryKey: ["admin", "products"],
    successMessage: () => `${product.name} deleted.`,
  });

  if (!confirming) {
    return (
      <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => setConfirming(true)}>
        Delete
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-slate-500 dark:text-slate-400">Delete permanently?</span>
      <Button variant="danger" className="px-2 py-1 text-xs" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate()}>
        {deleteMutation.isPending ? "…" : "Confirm"}
      </Button>
      <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setConfirming(false)}>
        Cancel
      </Button>
    </div>
  );
}

export function CompanyProductsPage() {
  const [selected, setSelected] = useState<AdminLoanProductResponse | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const navigate = useNavigate();

  const productsQuery = useQuery({
    queryKey: ["admin", "products"],
    queryFn: () => apiRequest<AdminLoanProductResponse[]>("/admin/products"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Products"
        subtitle="Your company's loan products and thresholds"
        actions={
          <>
            <Button variant="secondary" onClick={() => navigate("/admin/loans/calculator")}>
              Calculator
            </Button>
            <Button onClick={() => setCreateOpen(true)}>New product</Button>
          </>
        }
      />

      <Card>
        <DataTable
          columns={[
            { key: "name", header: "Product", sortable: true, accessor: (p: AdminLoanProductResponse) => p.name },
            {
              key: "range",
              header: "Range",
              accessor: (p) => Number(p.min_amount),
              render: (p) => `KES ${p.min_amount} – ${p.max_amount}`,
            },
            {
              key: "interest",
              header: "Interest",
              sortable: true,
              accessor: (p) => Number(p.interest_rate),
              render: (p) => `${p.interest_rate}% (${p.interest_model.replace(/_/g, " ")})`,
            },
            { key: "period", header: "Term", accessor: (p) => `${p.repayment_period_days}d` },
            {
              key: "guarantor",
              header: "Guarantor",
              accessor: (p) => (p.requires_guarantor ? "required" : "optional"),
              render: (p) => (p.requires_guarantor ? <Badge tone="warning">Required</Badge> : "—"),
            },
            {
              key: "status",
              header: "Status",
              accessor: (p) => (p.is_active ? "active" : "inactive"),
              render: (p) => <Badge tone={p.is_active ? "success" : "neutral"}>{p.is_active ? "Active" : "Inactive"}</Badge>,
            },
          ]}
          data={productsQuery.data}
          getRowId={(p) => p.id}
          isLoading={productsQuery.isLoading}
          isError={productsQuery.isError}
          emptyMessage="No products configured."
          onRowClick={(p) => setSelected(p)}
          rowActions={(p) => (
            <div className="flex items-center justify-end gap-3">
              <span className="text-xs text-slate-400 dark:text-slate-500">Click row to edit</span>
              <DeleteProductAction product={p} />
            </div>
          )}
        />
      </Card>

      <CreateProductDrawer open={createOpen} onClose={() => setCreateOpen(false)} />
      <EditProductDrawer product={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
