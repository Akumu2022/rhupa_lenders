import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, Field, PageHeader, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { useApiMutation } from "../../hooks/useApiMutation";
import { branchCreateSchema, type BranchCreateInput, type BranchResponse } from "../../schemas/admin";

function CreateBranchDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<BranchCreateInput>({ resolver: zodResolver(branchCreateSchema) });

  async function onSubmit(values: BranchCreateInput) {
    setError(null);
    try {
      const branch = await apiRequest<BranchResponse>("/admin/branches", { method: "POST", body: values });
      void queryClient.invalidateQueries({ queryKey: ["branches"] });
      toast(`${branch.name} created.`, "success");
      reset();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Create a branch">
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field label="Branch name" error={errors.name?.message}>
          <TextInput {...register("name")} />
        </Field>
        <Field label="Branch code" error={errors.code?.message}>
          <TextInput placeholder="e.g. NRB-01" {...register("code")} />
        </Field>
        <Field label="Address" error={errors.address?.message}>
          <TextInput {...register("address")} />
        </Field>
        {error ? <Banner kind="error">{error}</Banner> : null}
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Creating…" : "Create branch"}
        </Button>
      </form>
    </Drawer>
  );
}

function ActiveToggle({ branch }: { branch: BranchResponse }) {
  const toggle = useApiMutation({
    mutationFn: () =>
      apiRequest<BranchResponse>(`/admin/branches/${branch.id}`, {
        method: "PATCH",
        body: { is_active: !branch.is_active },
      }),
    queryKey: ["branches"],
    successMessage: (updated) => `${updated.name} ${updated.is_active ? "reactivated" : "deactivated"}.`,
  });

  return (
    <Button
      variant={branch.is_active ? "danger" : "secondary"}
      className="px-2 py-1 text-xs"
      disabled={toggle.isPending}
      onClick={() => toggle.mutate()}
    >
      {branch.is_active ? "Deactivate" : "Reactivate"}
    </Button>
  );
}

export function CompanyBranchesPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const branchesQuery = useQuery({
    queryKey: ["branches"],
    queryFn: () => apiRequest<BranchResponse[]>("/admin/branches"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Branches"
        subtitle="Your company's branch network"
        actions={<Button onClick={() => setDrawerOpen(true)}>Create branch</Button>}
      />

      <Card>
        <DataTable
          columns={[
            { key: "name", header: "Branch", sortable: true, accessor: (b: BranchResponse) => b.name },
            { key: "code", header: "Code", accessor: (b) => b.code },
            { key: "address", header: "Address", accessor: (b) => b.address ?? "—" },
            {
              key: "status",
              header: "Status",
              accessor: (b) => (b.is_active ? "active" : "inactive"),
              render: (b) => <Badge tone={b.is_active ? "success" : "neutral"}>{b.is_active ? "Active" : "Inactive"}</Badge>,
            },
          ]}
          data={branchesQuery.data}
          getRowId={(b) => b.id}
          isLoading={branchesQuery.isLoading}
          isError={branchesQuery.isError}
          searchKeys={["name", "code"]}
          searchPlaceholder="Search branches…"
          emptyMessage="No branches yet — create your first one before assigning branch staff."
          rowActions={(b) => <ActiveToggle branch={b} />}
        />
      </Card>

      <CreateBranchDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </AppShell>
  );
}
