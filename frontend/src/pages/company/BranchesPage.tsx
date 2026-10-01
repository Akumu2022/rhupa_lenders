import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, Field, PageHeader, Select, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { useApiMutation } from "../../hooks/useApiMutation";
import {
  branchCreateSchema,
  branchEditSchema,
  type BranchCreateInput,
  type BranchEditInput,
  type BranchResponse,
} from "../../schemas/admin";
import type { UserResponse } from "../../schemas/staff";
import { CopyLinkButton, NeedsBranchPanel, branchSignupUrl, useSignupCode } from "./BranchAssignmentPanel";

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

function EditBranchDrawer({ branch, onClose }: { branch: BranchResponse | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);

  const managersQuery = useQuery({
    queryKey: ["staff"],
    queryFn: () => apiRequest<UserResponse[]>("/staff"),
    enabled: branch !== null,
  });
  const managers = (managersQuery.data ?? []).filter((u) => u.role === "branch_manager");

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<BranchEditInput>({
    resolver: zodResolver(branchEditSchema),
    values: branch
      ? {
          name: branch.name,
          address: branch.address ?? "",
          manager_id: branch.manager_id ? String(branch.manager_id) : "",
          delegated_limit: branch.delegated_limit ?? "",
        }
      : undefined,
  });

  async function onSubmit(values: BranchEditInput) {
    if (!branch) return;
    setError(null);
    try {
      const updated = await apiRequest<BranchResponse>(`/admin/branches/${branch.id}`, {
        method: "PATCH",
        body: {
          name: values.name,
          address: values.address || null,
          manager_id: values.manager_id ? Number(values.manager_id) : null,
          delegated_limit: values.delegated_limit ? values.delegated_limit : null,
        },
      });
      void queryClient.invalidateQueries({ queryKey: ["branches"] });
      toast(`${updated.name} updated.`, "success");
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <Drawer open={branch !== null} onClose={onClose} title={branch ? `Edit ${branch.name}` : "Edit branch"}>
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field label="Branch name" error={errors.name?.message}>
          <TextInput {...register("name")} />
        </Field>
        <Field label="Branch code">
          <TextInput value={branch?.code ?? ""} disabled readOnly />
        </Field>
        <Field label="Address" error={errors.address?.message}>
          <TextInput {...register("address")} />
        </Field>
        <Field label="Branch manager" error={errors.manager_id?.message}>
          <Select {...register("manager_id")}>
            <option value="">— None —</option>
            {managers.map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Delegated approval limit (KES, optional)" error={errors.delegated_limit?.message}>
          <TextInput type="number" step="0.01" min="0" placeholder="Product default" {...register("delegated_limit")} />
        </Field>
        {error ? <Banner kind="error">{error}</Banner> : null}
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Saving…" : "Save changes"}
        </Button>
      </form>
    </Drawer>
  );
}

function DeleteBranchButton({ branch }: { branch: BranchResponse }) {
  const remove = useApiMutation({
    mutationFn: () => apiRequest<null>(`/admin/branches/${branch.id}`, { method: "DELETE" }),
    queryKey: ["branches"],
    successMessage: () => `${branch.name} deleted.`,
  });

  return (
    <Button
      variant="danger"
      className="px-2 py-1 text-xs"
      disabled={remove.isPending}
      onClick={() => {
        if (window.confirm(`Delete ${branch.name} (${branch.code})? This cannot be undone.`)) remove.mutate();
      }}
    >
      Delete
    </Button>
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
  const [editing, setEditing] = useState<BranchResponse | null>(null);

  const branchesQuery = useQuery({
    queryKey: ["branches"],
    queryFn: () => apiRequest<BranchResponse[]>("/admin/branches"),
  });
  const signupCode = useSignupCode().data?.signup_code;

  return (
    <AppShell>
      <PageHeader
        title="Branches"
        subtitle="Your company's branch network. Share a branch's signup link so new customers land in that branch."
        actions={<Button onClick={() => setDrawerOpen(true)}>Create branch</Button>}
      />

      {branchesQuery.data ? <NeedsBranchPanel branches={branchesQuery.data} /> : null}

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
          onRowClick={(b) => setEditing(b)}
          rowActions={(b) => (
            <div className="flex items-center gap-2">
              {signupCode && b.is_active ? <CopyLinkButton url={branchSignupUrl(signupCode, b.code)} /> : null}
              <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setEditing(b)}>
                Edit
              </Button>
              <ActiveToggle branch={b} />
              <DeleteBranchButton branch={b} />
            </div>
          )}
        />
      </Card>

      <CreateBranchDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      <EditBranchDrawer branch={editing} onClose={() => setEditing(null)} />
    </AppShell>
  );
}
