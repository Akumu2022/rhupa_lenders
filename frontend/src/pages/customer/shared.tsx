import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { apiRequestMultipart, buildMultipartForm, getErrorMessage } from "../../api/client";
import { FileDropzone } from "../../components/FileDropzone";
import { Banner, Button, Card, Field, TextInput } from "../../components/ui";
import { profileSubmitSchema, type ProfileSubmitInput } from "../../schemas/profile";
import type { LoanApplicationResponse } from "../../schemas/loan";

// CLAUDE.md §26 (M13): a submitted application is "in review" under one of
// three status values depending on how far it's gotten in the chain — all
// three read as the same warm/pending color, just with different labels.
const IN_REVIEW_STATUSES: LoanApplicationResponse["status"][] = [
  "pending",
  "pending_branch_review",
  "pending_committee_review",
];

export function applicationHasPendingDecision(applications: LoanApplicationResponse[]): boolean {
  return applications.some((a) => IN_REVIEW_STATUSES.includes(a.status));
}

export function applicationStatusTone(status: LoanApplicationResponse["status"]): "success" | "danger" | "warning" {
  if (status === "approved") return "success";
  if (status === "rejected") return "danger";
  return "warning";
}

export function applicationStatusLabel(status: LoanApplicationResponse["status"]): string {
  switch (status) {
    case "pending":
      return "Pending review";
    case "pending_branch_review":
      return "Awaiting branch review";
    case "pending_committee_review":
      return "Awaiting committee review";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
  }
}

export function loanStatusTone(status: string): "success" | "info" | "warning" | "danger" {
  if (status === "repaid") return "success";
  if (status === "active") return "info";
  if (status === "overdue") return "warning";
  if (status === "defaulted") return "danger";
  return "warning"; // approved (awaiting disbursement)
}

export function KycSubmitForm({
  onSubmitted,
  rejectionReason,
}: {
  onSubmitted: () => void;
  rejectionReason?: string | null;
}) {
  const [idFrontFile, setIdFrontFile] = useState<File | null>(null);
  const [idBackFile, setIdBackFile] = useState<File | null>(null);
  const [selfieFile, setSelfieFile] = useState<File | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ProfileSubmitInput>({ resolver: zodResolver(profileSubmitSchema) });

  async function onSubmit(values: ProfileSubmitInput) {
    setServerError(null);
    if (!idFrontFile) {
      setServerError("Please attach the front of your ID document");
      return;
    }
    if (!idBackFile) {
      setServerError("Please attach the back of your ID document");
      return;
    }
    const formData = buildMultipartForm(values, {
      id_document: idFrontFile,
      id_document_back: idBackFile,
      selfie_photo: selfieFile,
    });

    try {
      await apiRequestMultipart("/profile", formData);
      onSubmitted();
    } catch (err) {
      setServerError(getErrorMessage(err));
    }
  }

  return (
    <Card>
      {rejectionReason ? (
        <div className="mb-4">
          <Banner kind="error">
            Your previous submission was rejected: "{rejectionReason}". Please correct the details below and
            resubmit.
          </Banner>
        </div>
      ) : null}
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field label="Date of birth" error={errors.date_of_birth?.message}>
          <TextInput type="date" {...register("date_of_birth")} />
        </Field>
        <Field label="National ID number" error={errors.national_id_number?.message}>
          <TextInput {...register("national_id_number")} />
        </Field>
        <Field label="Phone number" error={errors.phone_number?.message}>
          <TextInput {...register("phone_number")} />
        </Field>
        <Field label="Residential address" error={errors.residential_address?.message}>
          <TextInput {...register("residential_address")} />
        </Field>
        <Field label="Employment status" error={errors.employment_status?.message}>
          <TextInput {...register("employment_status")} />
        </Field>
        <Field label="Monthly income (KES)" error={errors.monthly_income?.message}>
          <TextInput type="number" step="0.01" min="0" {...register("monthly_income")} />
        </Field>
        <Field label="Occupation" error={errors.occupation?.message}>
          <TextInput {...register("occupation")} />
        </Field>
        <FileDropzone
          label="ID document — front"
          accept=".jpg,.jpeg,.png,.pdf"
          file={idFrontFile}
          onChange={setIdFrontFile}
          hint="JPG, PNG, or PDF"
        />
        <FileDropzone
          label="ID document — back"
          accept=".jpg,.jpeg,.png,.pdf"
          file={idBackFile}
          onChange={setIdBackFile}
          hint="JPG, PNG, or PDF"
        />
        <FileDropzone
          label="Selfie / passport photo (optional)"
          accept=".jpg,.jpeg,.png"
          file={selfieFile}
          onChange={setSelfieFile}
          hint="JPG or PNG"
        />
        {serverError ? <Banner kind="error">{serverError}</Banner> : null}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Submitting…" : "Submit for verification"}
        </Button>
      </form>
    </Card>
  );
}
