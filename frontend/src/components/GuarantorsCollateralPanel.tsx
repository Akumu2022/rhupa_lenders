import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { apiRequest, getErrorMessage } from "../api/client";
import { Badge, Banner, Button, EmptyState, Field, SectionLabel, TextInput } from "./ui";
import { useToast } from "./toast";
import {
  guarantorInputSchema,
  guarantorStatusTone,
  securityInputSchema,
  type GuarantorInputForm,
  type GuarantorResponse,
  type SecurityInputForm,
  type SecurityResponse,
} from "../schemas/guarantor";

/** CLAUDE.md §27 (M12): shared guarantors/collateral view for one loan
 * application. `editable` (credit officer, preparing the application) shows
 * add/verify forms; read-only (branch manager/committee, deciding it) shows
 * the same data without the ability to change it. */
export function GuarantorsCollateralPanel({
  applicationId,
  editable = false,
}: {
  applicationId: number;
  editable?: boolean;
}) {
  return (
    <div className="space-y-4">
      <GuarantorsList applicationId={applicationId} editable={editable} />
      <CollateralList applicationId={applicationId} editable={editable} />
    </div>
  );
}

function GuarantorsList({ applicationId, editable }: { applicationId: number; editable: boolean }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);

  const guarantorsQuery = useQuery({
    queryKey: ["applications", applicationId, "guarantors"],
    queryFn: () => apiRequest<GuarantorResponse[]>(`/applications/${applicationId}/guarantors`),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<GuarantorInputForm>({ resolver: zodResolver(guarantorInputSchema) });

  async function onSubmit(values: GuarantorInputForm) {
    try {
      await apiRequest(`/applications/${applicationId}/guarantors`, { method: "POST", body: values });
      void queryClient.invalidateQueries({ queryKey: ["applications", applicationId, "guarantors"] });
      toast("Guarantor added.", "success");
      reset();
      setAdding(false);
    } catch (err) {
      toast(getErrorMessage(err), "error");
    }
  }

  const verify = useMutation({
    mutationFn: (guarantorId: number) =>
      apiRequest<GuarantorResponse>(`/applications/${applicationId}/guarantors/${guarantorId}`, {
        method: "PATCH",
        body: { verification_status: "verified" },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["applications", applicationId, "guarantors"] });
      toast("Guarantor verified.", "success");
    },
    onError: (err) => toast(getErrorMessage(err), "error"),
  });

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <SectionLabel>Guarantors</SectionLabel>
        {editable && !adding ? (
          <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setAdding(true)}>
            Add guarantor
          </Button>
        ) : null}
      </div>

      {guarantorsQuery.data && guarantorsQuery.data.length > 0 ? (
        <ul className="space-y-2 text-sm">
          {guarantorsQuery.data.map((g) => (
            <li
              key={g.id}
              className="flex items-center justify-between rounded-lg border border-slate-200 p-3 dark:border-slate-700"
            >
              <div>
                <p className="font-medium text-slate-900 dark:text-slate-100">{g.full_name}</p>
                <p className="text-slate-500 dark:text-slate-400">
                  {g.id_number} · {g.phone_number} · KES {g.guaranteed_amount}
                  {g.relationship ? ` · ${g.relationship}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={guarantorStatusTone(g.verification_status)}>{g.verification_status}</Badge>
                {editable && g.verification_status === "pending" ? (
                  <Button
                    variant="secondary"
                    className="px-2 py-1 text-xs"
                    disabled={verify.isPending}
                    onClick={() => verify.mutate(g.id)}
                  >
                    Verify
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : !adding ? (
        <EmptyState>No guarantors attached yet.</EmptyState>
      ) : null}

      {adding ? (
        <form className="mt-3 space-y-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Full name" error={errors.full_name?.message}>
              <TextInput {...register("full_name")} />
            </Field>
            <Field label="ID number" error={errors.id_number?.message}>
              <TextInput {...register("id_number")} />
            </Field>
            <Field label="Phone number" error={errors.phone_number?.message}>
              <TextInput {...register("phone_number")} />
            </Field>
            <Field label="Guaranteed amount (KES)" error={errors.guaranteed_amount?.message}>
              <TextInput type="number" step="0.01" min="0" {...register("guaranteed_amount")} />
            </Field>
            <Field label="Relationship (optional)" error={errors.relationship?.message}>
              <TextInput {...register("relationship")} />
            </Field>
            <Field label="Occupation (optional)" error={errors.occupation?.message}>
              <TextInput {...register("occupation")} />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <input type="checkbox" className="h-4 w-4 rounded border-slate-300" {...register("consent")} />
            Guarantor has given consent
          </label>
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
    </div>
  );
}

function CollateralList({ applicationId, editable }: { applicationId: number; editable: boolean }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const collateralQuery = useQuery({
    queryKey: ["applications", applicationId, "collateral"],
    queryFn: () => apiRequest<SecurityResponse[]>(`/applications/${applicationId}/collateral`),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<SecurityInputForm>({ resolver: zodResolver(securityInputSchema) });

  async function onSubmit(values: SecurityInputForm) {
    setServerError(null);
    try {
      await apiRequest(`/applications/${applicationId}/collateral`, { method: "POST", body: values });
      void queryClient.invalidateQueries({ queryKey: ["applications", applicationId, "collateral"] });
      toast("Collateral added.", "success");
      reset();
      setAdding(false);
    } catch (err) {
      setServerError(getErrorMessage(err));
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <SectionLabel>Collateral</SectionLabel>
        {editable && !adding ? (
          <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setAdding(true)}>
            Add collateral
          </Button>
        ) : null}
      </div>

      {collateralQuery.data && collateralQuery.data.length > 0 ? (
        <ul className="space-y-2 text-sm">
          {collateralQuery.data.map((s) => (
            <li key={s.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <p className="font-medium text-slate-900 dark:text-slate-100">{s.description}</p>
              <p className="text-slate-500 dark:text-slate-400">Estimated value: KES {s.estimated_value}</p>
            </li>
          ))}
        </ul>
      ) : !adding ? (
        <EmptyState>No collateral pledged yet.</EmptyState>
      ) : null}

      {adding ? (
        <form className="mt-3 space-y-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <Field label="Description" error={errors.description?.message}>
            <TextInput {...register("description")} />
          </Field>
          <Field label="Estimated value (KES)" error={errors.estimated_value?.message}>
            <TextInput type="number" step="0.01" min="0" {...register("estimated_value")} />
          </Field>
          {serverError ? <Banner kind="error">{serverError}</Banner> : null}
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
    </div>
  );
}
