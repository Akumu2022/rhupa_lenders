import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import {
  Badge,
  Banner,
  Button,
  Card,
  Field,
  PageHeader,
  PasswordInput,
  SectionLabel,
  Sparkline,
  StatCard,
  TextInput,
} from "../../components/ui";
import { ColorField } from "../../components/ColorField";
import { ImageFileField } from "../../components/FileDropzone";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { useApiMutation } from "../../hooks/useApiMutation";
import {
  companyCreateSchema,
  omitBlankFields,
  platformPasswordResetSchema,
  type CompanyActivityResponse,
  type CompanyCreateInput,
  type CompanyDetailResponse,
  type CompanyResponse,
  type CompanyUserRow,
  type PlatformPasswordResetInput,
} from "../../schemas/company";

function CreateCompanyDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const [createdCode, setCreatedCode] = useState<string | null>(null);
  const closeTimerRef = useRef<number | null>(null);

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CompanyCreateInput>({ resolver: zodResolver(companyCreateSchema) });

  // Clear any pending auto-close timer if the drawer unmounts first (e.g.
  // the admin navigates away right after creating a company).
  useEffect(
    () => () => {
      if (closeTimerRef.current) window.clearTimeout(closeTimerRef.current);
    },
    [],
  );

  function closeDrawer() {
    if (closeTimerRef.current) window.clearTimeout(closeTimerRef.current);
    setCreatedCode(null);
    onClose();
  }

  async function onSubmit(values: CompanyCreateInput) {
    setError(null);
    try {
      const company = await apiRequest<CompanyResponse>("/platform/companies", {
        method: "POST",
        body: omitBlankFields(values),
      });
      setCreatedCode(company.signup_code);
      reset();
      void queryClient.invalidateQueries({ queryKey: ["platform", "companies"] });
      toast(`${company.name} created.`, "success");
      // Auto-close after a moment — long enough to read the signup code
      // banner below, short enough that the drawer doesn't just sit there
      // needing a manual close. The code and every other detail remain
      // visible afterward in the companies table (§18: nothing shown once
      // and lost).
      closeTimerRef.current = window.setTimeout(closeDrawer, 2000);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <Drawer open={open} onClose={closeDrawer} title="Create a company">
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field label="Company name" error={errors.name?.message}>
          <TextInput {...register("name")} />
        </Field>
        <Field label="First admin's full name" error={errors.admin_full_name?.message}>
          <TextInput {...register("admin_full_name")} />
        </Field>
        <Field label="First admin's email" error={errors.admin_email?.message}>
          <TextInput type="email" {...register("admin_email")} />
        </Field>
        <Field label="First admin's password" error={errors.admin_password?.message}>
          <PasswordInput {...register("admin_password")} />
        </Field>

        <SectionLabel>Profile &amp; branding (optional)</SectionLabel>
        <Field label="Legal name" error={errors.legal_name?.message}>
          <TextInput {...register("legal_name")} />
        </Field>
        <Field label="Business registration number" error={errors.registration_number?.message}>
          <TextInput {...register("registration_number")} />
        </Field>
        <Field label="Support email" error={errors.support_email?.message}>
          <TextInput type="email" {...register("support_email")} />
        </Field>
        <Field label="Support phone" error={errors.support_phone?.message}>
          <TextInput {...register("support_phone")} />
        </Field>
        <Field label="Address" error={errors.address?.message}>
          <TextInput {...register("address")} />
        </Field>
        <Controller
          control={control}
          name="logo_url"
          render={({ field }) => (
            <ImageFileField label="Logo" value={field.value} onChange={field.onChange} />
          )}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Controller
            control={control}
            name="brand_primary_color"
            render={({ field }) => (
              <ColorField
                label="Brand primary color"
                value={field.value}
                onChange={field.onChange}
                error={errors.brand_primary_color?.message}
                placeholder="#4F46E5"
              />
            )}
          />
          <Controller
            control={control}
            name="brand_accent_color"
            render={({ field }) => (
              <ColorField
                label="Brand accent color"
                value={field.value}
                onChange={field.onChange}
                error={errors.brand_accent_color?.message}
                placeholder="#7C3AED"
              />
            )}
          />
        </div>

        {error ? <Banner kind="error">{error}</Banner> : null}
        {createdCode ? (
          <Banner kind="success">
            Company created. Signup code: <span className="font-mono">{createdCode}</span>
          </Banner>
        ) : null}
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Creating…" : "Create company"}
        </Button>
      </form>
    </Drawer>
  );
}

function SuspensionAction({ company }: { company: CompanyResponse }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const toggle = useApiMutation({
    mutationFn: async () => {
      const action = company.status === "active" ? "suspend" : "reactivate";
      return apiRequest<CompanyResponse>(`/platform/companies/${company.id}/${action}`, {
        method: "POST",
        body: { reason },
      });
    },
    queryKey: ["platform", "companies"],
    successMessage: (updated) => `${updated.name} ${updated.status === "active" ? "reactivated" : "suspended"}.`,
    onSuccess: () => {
      setReason("");
      setError(null);
      setOpen(false);
    },
    onError: setError,
  });

  if (!open) {
    return (
      <Button variant={company.status === "active" ? "danger" : "secondary"} className="px-2 py-1 text-xs" onClick={() => setOpen(true)}>
        {company.status === "active" ? "Suspend" : "Reactivate"}
      </Button>
    );
  }

  return (
    <div className="flex items-center justify-end gap-2">
      <TextInput
        placeholder="Reason (required)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="w-40 py-1 text-xs"
      />
      <Button
        variant={company.status === "active" ? "danger" : "secondary"}
        className="px-2 py-1 text-xs"
        disabled={!reason.trim() || toggle.isPending}
        onClick={() => toggle.mutate()}
      >
        Confirm
      </Button>
      {error ? <span className="text-xs text-rose-600 dark:text-rose-400">{error}</span> : null}
    </div>
  );
}

function ResetUserPasswordAction({ user }: { user: CompanyUserRow }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PlatformPasswordResetInput>({ resolver: zodResolver(platformPasswordResetSchema) });

  async function onSubmit(values: PlatformPasswordResetInput) {
    setError(null);
    try {
      await apiRequest(`/platform/users/${user.id}/reset-password`, { method: "POST", body: values });
      reset();
      setOpen(false);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  if (!open) {
    return (
      <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setOpen(true)}>
        Reset password
      </Button>
    );
  }

  return (
    <form className="space-y-2" onSubmit={handleSubmit(onSubmit)} noValidate>
      <PasswordInput placeholder="New password" className="py-1 text-xs" {...register("new_password")} />
      {errors.new_password ? <p className="text-xs text-rose-600 dark:text-rose-400">{errors.new_password.message}</p> : null}
      <TextInput placeholder="Reason (required)" className="py-1 text-xs" {...register("reason")} />
      {errors.reason ? <p className="text-xs text-rose-600 dark:text-rose-400">{errors.reason.message}</p> : null}
      {error ? <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p> : null}
      <div className="flex gap-2">
        <Button type="submit" className="px-2 py-1 text-xs" disabled={isSubmitting}>
          {isSubmitting ? "Resetting…" : "Confirm reset"}
        </Button>
        <Button type="button" variant="secondary" className="px-2 py-1 text-xs" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Super_admin support screen for one company: staff/customer counts, a
 * 30-day activity trend (free from the existing AuditLog — no new
 * instrumentation, see app/routers/platform.py::get_company_activity), and
 * the ability to reset any of this company's users' passwords if they're
 * locked out. */
function CompanyDetailDrawer({ companyId, onClose }: { companyId: number | null; onClose: () => void }) {
  const detailQuery = useQuery({
    queryKey: ["platform", "companies", companyId],
    queryFn: () => apiRequest<CompanyDetailResponse>(`/platform/companies/${companyId}`),
    enabled: companyId !== null,
  });
  const usersQuery = useQuery({
    queryKey: ["platform", "companies", companyId, "users"],
    queryFn: () => apiRequest<CompanyUserRow[]>(`/platform/companies/${companyId}/users`),
    enabled: companyId !== null,
  });
  const activityQuery = useQuery({
    queryKey: ["platform", "companies", companyId, "activity"],
    queryFn: () => apiRequest<CompanyActivityResponse>(`/platform/companies/${companyId}/activity`),
    enabled: companyId !== null,
  });

  const company = detailQuery.data;

  return (
    <Drawer open={companyId !== null} onClose={onClose} title={company ? company.name : "Company"}>
      {company ? (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <Badge tone={company.status === "active" ? "success" : "danger"}>{company.status}</Badge>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Created {new Date(company.created_at).toLocaleDateString()}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <StatCard label="Staff" value={company.users.staff_total} tone="brand" icon="users" />
            <StatCard label="Customers" value={company.users.customer_total} tone="brand" icon="user" />
            <StatCard label="Staff inactive" value={company.users.staff_inactive} tone="neutral" />
            <StatCard label="Customers inactive" value={company.users.customer_inactive} tone="neutral" />
          </div>

          <div>
            <SectionLabel>Activity (last 30 days)</SectionLabel>
            {activityQuery.data ? (
              activityQuery.data.points.some((p) => p.audit_log_count > 0) ? (
                <>
                  <Sparkline
                    data={activityQuery.data.points.map((p) => p.audit_log_count)}
                    showArea
                    formatValue={(v) => `${v} action${v === 1 ? "" : "s"}`}
                  />
                  <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                    {activityQuery.data.last_activity_at
                      ? `Last activity ${new Date(activityQuery.data.last_activity_at).toLocaleString()}`
                      : "No recorded activity yet."}
                  </p>
                </>
              ) : (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  No activity in the last 30 days — this company may no longer be operational.
                </p>
              )
            ) : null}
          </div>

          <div>
            <SectionLabel>Users</SectionLabel>
            <DataTable
              columns={[
                { key: "name", header: "Name", accessor: (u: CompanyUserRow) => u.full_name },
                { key: "email", header: "Email", accessor: (u) => u.email },
                {
                  key: "role",
                  header: "Role",
                  accessor: (u) => u.role,
                  render: (u) => <Badge tone="brand">{u.role.replace(/_/g, " ")}</Badge>,
                },
                {
                  key: "status",
                  header: "Status",
                  accessor: (u) => (u.is_active ? "active" : "inactive"),
                  render: (u) => <Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "Active" : "Inactive"}</Badge>,
                },
              ]}
              data={usersQuery.data}
              getRowId={(u) => u.id}
              isLoading={usersQuery.isLoading}
              isError={usersQuery.isError}
              pageSize={5}
              emptyMessage="No users yet."
              rowActions={(u) => <ResetUserPasswordAction user={u} />}
            />
          </div>
        </div>
      ) : (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
      )}
    </Drawer>
  );
}

export function PlatformCompaniesPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);

  const companiesQuery = useQuery({
    queryKey: ["platform", "companies"],
    queryFn: () => apiRequest<CompanyResponse[]>("/platform/companies"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Companies"
        subtitle="Every tenant on the platform — click a row for usage details"
        actions={<Button onClick={() => setDrawerOpen(true)}>Create company</Button>}
      />

      <Card>
        <DataTable
          columns={[
            { key: "name", header: "Company", sortable: true, accessor: (c: CompanyResponse) => c.name },
            {
              key: "status",
              header: "Status",
              accessor: (c) => c.status,
              render: (c) => <Badge tone={c.status === "active" ? "success" : "danger"}>{c.status}</Badge>,
            },
            {
              key: "signup_code",
              header: "Signup code",
              accessor: (c) => c.signup_code,
              render: (c) => <span className="font-mono text-xs">{c.signup_code}</span>,
            },
            {
              key: "created_at",
              header: "Created",
              sortable: true,
              accessor: (c) => c.created_at,
              render: (c) => new Date(c.created_at).toLocaleDateString(),
            },
          ]}
          data={companiesQuery.data}
          getRowId={(c) => c.id}
          isLoading={companiesQuery.isLoading}
          isError={companiesQuery.isError}
          searchKeys={["name"]}
          searchPlaceholder="Search companies…"
          emptyMessage="No companies yet."
          onRowClick={(c) => setSelectedCompanyId(c.id)}
          rowActions={(c) => <SuspensionAction company={c} />}
        />
      </Card>

      <CreateCompanyDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      <CompanyDetailDrawer companyId={selectedCompanyId} onClose={() => setSelectedCompanyId(null)} />
    </AppShell>
  );
}
