import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Banner, Button, Card, Field, PageHeader, SectionLabel, TextInput } from "../../components/ui";
import { ColorField } from "../../components/ColorField";
import { ImageFileField } from "../../components/FileDropzone";
import { safeHex } from "../../branding";
import { useToast } from "../../components/toast";
import {
  companyProfileUpdateSchema,
  omitBlankFields,
  type CompanyInfoResponse,
  type CompanyProfileUpdateInput,
} from "../../schemas/company";

export function CompanyProfilePage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);

  const companyQuery = useQuery({
    queryKey: ["companies", "me"],
    queryFn: () => apiRequest<CompanyInfoResponse>("/companies/me"),
  });

  const {
    register,
    control,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<CompanyProfileUpdateInput>({ resolver: zodResolver(companyProfileUpdateSchema) });

  const liveValues = watch();
  const previewPrimary = safeHex(liveValues.brand_primary_color) ?? "#4F46E5";
  const previewAccent = safeHex(liveValues.brand_accent_color) ?? previewPrimary;

  useEffect(() => {
    if (companyQuery.data) {
      reset({
        tagline: companyQuery.data.tagline ?? "",
        logo_url: companyQuery.data.logo_url ?? "",
        brand_primary_color: companyQuery.data.brand_primary_color ?? "",
        brand_accent_color: companyQuery.data.brand_accent_color ?? "",
        support_email: companyQuery.data.support_email ?? "",
        support_phone: companyQuery.data.support_phone ?? "",
        address: companyQuery.data.address ?? "",
      });
    }
  }, [companyQuery.data, reset]);

  async function onSubmit(values: CompanyProfileUpdateInput) {
    setError(null);
    try {
      await apiRequest("/companies/me", { method: "PATCH", body: omitBlankFields(values) });
      void queryClient.invalidateQueries({ queryKey: ["companies", "me"] });
      toast("Company profile updated.", "success");
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="Company profile"
        subtitle="Contacts, address, logo, and brand colors shown to your staff and customers"
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <Card className="lg:col-span-7">
        {companyQuery.isLoading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
        ) : (
          <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <Field label="Tagline" error={errors.tagline?.message}>
              <TextInput placeholder="A short motto shown under your name" {...register("tagline")} />
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
            <Field label="Support email" error={errors.support_email?.message}>
              <TextInput type="email" {...register("support_email")} />
            </Field>
            <Field label="Support phone" error={errors.support_phone?.message}>
              <TextInput {...register("support_phone")} />
            </Field>
            <Field label="Address" error={errors.address?.message}>
              <TextInput {...register("address")} />
            </Field>
            {error ? <Banner kind="error">{error}</Banner> : null}
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : "Save changes"}
            </Button>
          </form>
        )}
      </Card>

      {/* Live preview so a saved change is visibly confirmed right here,
          not just via a toast — the sidebar mark/name and primary button
          across the app pick up the same saved values (CLAUDE.md §21). */}
      <Card className="lg:col-span-5">
        <SectionLabel>Live preview</SectionLabel>
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2.5 border-b border-slate-100 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
            {liveValues.logo_url ? (
              <img src={liveValues.logo_url} alt="" className="h-8 w-8 rounded-lg object-cover" />
            ) : (
              <span
                className="flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold text-white"
                style={{ backgroundImage: `linear-gradient(135deg, ${previewPrimary}, ${previewAccent})` }}
              >
                {(companyQuery.data?.name ?? "R").charAt(0).toUpperCase()}
              </span>
            )}
            <div className="min-w-0 leading-tight">
              <p className="truncate text-sm font-bold text-slate-900 dark:text-slate-50">{companyQuery.data?.name}</p>
              <p className="truncate text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
                {liveValues.tagline || "Lending Platform"}
              </p>
            </div>
          </div>
          <div className="space-y-2 bg-slate-50 p-4 dark:bg-slate-950">
            <button
              type="button"
              disabled
              className="w-full rounded-lg px-4 py-2 text-sm font-semibold text-white"
              style={{ backgroundImage: `linear-gradient(to right, ${previewPrimary}, ${previewAccent})` }}
            >
              Primary button
            </button>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              This is how your sidebar mark and primary buttons will look across the app.
            </p>
          </div>
        </div>
      </Card>
      </div>
    </AppShell>
  );
}
