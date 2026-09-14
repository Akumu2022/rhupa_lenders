import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, Field, PageHeader, Select, TextInput } from "../../components/ui";
import { Combobox } from "../../components/Combobox";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { useApiMutation } from "../../hooks/useApiMutation";
import type { BranchResponse } from "../../schemas/admin";
import { BRANCH_REQUIRED_ROLES, staffCreateSchema, type StaffCreateInput, type UserResponse } from "../../schemas/staff";

const ROLE_LABELS: Record<string, string> = {
  credit_officer: "Credit officer",
  branch_manager: "Branch manager",
  loan_vetting_committee: "Loan vetting committee",
  cashier_finance_officer: "Cashier / Finance officer",
  management: "Management",
};

function AddStaffDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);

  const branchesQuery = useQuery({
    queryKey: ["branches"],
    queryFn: () => apiRequest<BranchResponse[]>("/admin/branches"),
    enabled: open,
  });

  const {
    register,
    control,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<StaffCreateInput>({
    resolver: zodResolver(staffCreateSchema),
    defaultValues: { role: "credit_officer", branch_id: "" },
  });

  const selectedRole = watch("role");
  const branchRequired = BRANCH_REQUIRED_ROLES.has(selectedRole);

  // CLAUDE.md §25: system_administrator is the only role that creates
  // branches. Rather than send them away from "Add staff" to a separate
  // page and back the moment they hit "Branch is required for this role"
  // with an empty list, let them write a branch right here — the newly
  // created branch is then immediately selectable (here, and for every
  // other staff member added afterward).
  const [creatingBranch, setCreatingBranch] = useState(false);
  const [newBranchName, setNewBranchName] = useState("");
  const [newBranchCode, setNewBranchCode] = useState("");
  const [branchError, setBranchError] = useState<string | null>(null);

  const createBranch = useApiMutation<BranchResponse>({
    mutationFn: () =>
      apiRequest<BranchResponse>("/admin/branches", {
        method: "POST",
        body: { name: newBranchName.trim(), code: newBranchCode.trim() },
      }),
    queryKey: ["branches"],
    successMessage: (branch) => `${branch.name} created and selected.`,
    onSuccess: (branch) => {
      setValue("branch_id", String(branch.id), { shouldValidate: true });
      setCreatingBranch(false);
      setNewBranchName("");
      setNewBranchCode("");
      setBranchError(null);
    },
    onError: setBranchError,
  });

  async function onSubmit(values: StaffCreateInput) {
    setError(null);
    try {
      // company_id is inherited server-side from the admin's own token (CLAUDE.md §4).
      const staff = await apiRequest<UserResponse>("/staff", {
        method: "POST",
        body: { ...values, branch_id: values.branch_id ? Number(values.branch_id) : undefined },
      });
      void queryClient.invalidateQueries({ queryKey: ["staff"] });
      toast(`${staff.full_name} added as ${staff.role.replace(/_/g, " ")}.`, "success");
      reset({ role: values.role });
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Add staff">
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field label="Full name" error={errors.full_name?.message}>
          <TextInput {...register("full_name")} />
        </Field>
        <Field label="Email" error={errors.email?.message}>
          <TextInput type="email" {...register("email")} />
        </Field>
        <Field label="Password" error={errors.password?.message}>
          <TextInput type="password" {...register("password")} />
        </Field>
        <Field label="Role" error={errors.role?.message}>
          <Select {...register("role")}>
            {Object.entries(ROLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        {/* CLAUDE.md §25: required for credit_officer/branch_manager only —
            those two roles are the ones scoped to a single branch. Type to
            search when a company has many branches; the committed value is
            still always one of the fetched branches, never free text — the
            server independently validates branch_id belongs to this
            admin's own company regardless (CLAUDE.md §4). */}
        <Field label={branchRequired ? "Branch" : "Branch (optional)"} error={errors.branch_id?.message}>
          <Controller
            control={control}
            name="branch_id"
            render={({ field }) => (
              <Combobox
                value={field.value ?? ""}
                onChange={field.onChange}
                disabled={branchesQuery.isLoading}
                placeholder={
                  branchesQuery.isLoading
                    ? "Loading branches…"
                    : branchRequired
                      ? "Type to search branches…"
                      : "Company-wide (no branch)"
                }
                options={(branchesQuery.data ?? []).map((branch) => ({
                  value: String(branch.id),
                  label: `${branch.name} (${branch.code})`,
                }))}
              />
            )}
          />
          {creatingBranch ? (
            <div className="mt-2 space-y-2 rounded-lg border border-dashed border-slate-300 p-3 dark:border-slate-700">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">New branch</p>
              <TextInput
                placeholder="Branch name"
                value={newBranchName}
                onChange={(e) => setNewBranchName(e.target.value)}
              />
              <TextInput
                placeholder="Branch code, e.g. NRB-01"
                value={newBranchCode}
                onChange={(e) => setNewBranchCode(e.target.value)}
              />
              {branchError ? <p className="text-xs text-rose-600 dark:text-rose-400">{branchError}</p> : null}
              <div className="flex gap-2">
                <Button
                  type="button"
                  className="flex-1"
                  disabled={!newBranchName.trim() || !newBranchCode.trim() || createBranch.isPending}
                  onClick={() => createBranch.mutate()}
                >
                  {createBranch.isPending ? "Creating…" : "Create & select"}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setCreatingBranch(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setCreatingBranch(true)}
              className="mt-2 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
            >
              + Create a new branch
            </button>
          )}
        </Field>
        {error ? <Banner kind="error">{error}</Banner> : null}
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Adding…" : "Add staff member"}
        </Button>
      </form>
    </Drawer>
  );
}

function StatusToggle({ staff }: { staff: UserResponse }) {
  const toggle = useApiMutation({
    mutationFn: () =>
      apiRequest<UserResponse>(`/staff/${staff.id}/${staff.is_active ? "deactivate" : "reactivate"}`, {
        method: "POST",
      }),
    queryKey: ["staff"],
    successMessage: (updated) => `${updated.full_name} ${updated.is_active ? "reactivated" : "deactivated"}.`,
  });

  return (
    <Button
      variant={staff.is_active ? "danger" : "secondary"}
      className="px-2 py-1 text-xs"
      disabled={toggle.isPending}
      onClick={() => toggle.mutate()}
    >
      {staff.is_active ? "Deactivate" : "Reactivate"}
    </Button>
  );
}

export function CompanyAdminUsersPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const staffQuery = useQuery({
    queryKey: ["staff"],
    queryFn: () => apiRequest<UserResponse[]>("/staff"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Users"
        subtitle="Branch and company-wide staff in your company"
        actions={<Button onClick={() => setDrawerOpen(true)}>Add staff</Button>}
      />

      <Card>
        <DataTable
          columns={[
            { key: "name", header: "Name", sortable: true, accessor: (s: UserResponse) => s.full_name },
            { key: "email", header: "Email", accessor: (s) => s.email },
            {
              key: "role",
              header: "Role",
              accessor: (s) => s.role,
              render: (s) => <Badge tone="brand">{s.role.replace(/_/g, " ")}</Badge>,
            },
            {
              key: "status",
              header: "Status",
              accessor: (s) => (s.is_active ? "active" : "inactive"),
              render: (s) => <Badge tone={s.is_active ? "success" : "neutral"}>{s.is_active ? "Active" : "Inactive"}</Badge>,
            },
          ]}
          data={staffQuery.data}
          getRowId={(s) => s.id}
          isLoading={staffQuery.isLoading}
          isError={staffQuery.isError}
          searchKeys={["name", "email"]}
          searchPlaceholder="Search staff…"
          emptyMessage="No staff yet — add your first branch or company-wide team member."
          rowActions={(s) => <StatusToggle staff={s} />}
        />
      </Card>

      <AddStaffDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </AppShell>
  );
}
