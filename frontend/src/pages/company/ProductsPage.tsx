import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, Field, PageHeader, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { productUpdateSchema, type AdminLoanProductResponse, type ProductUpdateInput } from "../../schemas/admin";

function EditProductDrawer({ product, onClose }: { product: AdminLoanProductResponse | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
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
      });
    }
  }, [product, reset]);

  async function onSubmit(values: ProductUpdateInput) {
    if (!product) return;
    setError(null);
    try {
      await apiRequest(`/admin/products/${product.id}`, {
        method: "PATCH",
        body: { ...values, repayment_period_days: Number(values.repayment_period_days) },
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

          <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
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

export function CompanyProductsPage() {
  const [selected, setSelected] = useState<AdminLoanProductResponse | null>(null);

  const productsQuery = useQuery({
    queryKey: ["admin", "products"],
    queryFn: () => apiRequest<AdminLoanProductResponse[]>("/admin/products"),
  });

  return (
    <AppShell>
      <PageHeader title="Products" subtitle="Your company's loan products and thresholds" />

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
              render: (p) => `${p.interest_rate}%`,
            },
            { key: "period", header: "Term", accessor: (p) => `${p.repayment_period_days}d` },
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
          rowActions={() => <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">Edit →</span>}
        />
      </Card>

      <EditProductDrawer product={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
