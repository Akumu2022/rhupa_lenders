import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, Field, PageHeader, SectionLabel, TextInput } from "../../components/ui";
import { ColorField } from "../../components/ColorField";
import { ImageFileField } from "../../components/FileDropzone";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { useApiMutation } from "../../hooks/useApiMutation";
import { companyCreateSchema, omitBlankFields, type CompanyCreateInput, type CompanyResponse } from "../../schemas/company";

function CreateCompanyDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const [createdCode, setCreatedCode] = useState<string | null>(null);

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CompanyCreateInput>({ resolver: zodResolver(companyCreateSchema) });

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
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <Drawer
      open={open}
      onClose={() => {
        setCreatedCode(null);
        onClose();
      }}
      title="Create a company"
    >
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
          <TextInput type="password" {...register("admin_password")} />
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

export function PlatformCompaniesPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const companiesQuery = useQuery({
    queryKey: ["platform", "companies"],
    queryFn: () => apiRequest<CompanyResponse[]>("/platform/companies"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Companies"
        subtitle="Every tenant on the platform"
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
          ]}
          data={companiesQuery.data}
          getRowId={(c) => c.id}
          isLoading={companiesQuery.isLoading}
          isError={companiesQuery.isError}
          searchKeys={["name"]}
          searchPlaceholder="Search companies…"
          emptyMessage="No companies yet."
          rowActions={(c) => <SuspensionAction company={c} />}
        />
      </Card>

      <CreateCompanyDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </AppShell>
  );
}
