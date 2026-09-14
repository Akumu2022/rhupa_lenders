import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { apiRequestMultipart, buildMultipartForm, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { FileDropzone } from "../../components/FileDropzone";
import { Banner, Button, Card, Field, PageHeader, Select, SectionLabel, TextInput } from "../../components/ui";
import {
  customerRegisterSchema,
  EMPLOYMENT_STATUS_OPTIONS,
  GENDER_OPTIONS,
  MARITAL_STATUS_OPTIONS,
  NATIONALITY_OPTIONS,
  NEXT_OF_KIN_RELATIONSHIP_OPTIONS,
  type CustomerRegisterInput,
  type CustomerResponse,
} from "../../schemas/customers";

// A customer must be at least 18 — same rule the Zod schema enforces —
// expressed here as the <input type="date"> max attribute so the native
// date picker itself won't offer a disqualifying date.
function maxDateOfBirth(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 18);
  return d.toISOString().slice(0, 10);
}

/**
 * CLAUDE.md §27 (M11): the credit officer's in-branch "New Customer" intake
 * — a full registration, unlike the lighter self-signup + self-KYC flow
 * (customer/SignupPage.tsx + customer/shared.tsx::KycSubmitForm) which
 * stays unchanged. Sectioned (§18/§20 density-with-discipline) so the long
 * field set stays scannable.
 */
export function RegisterCustomerPage() {
  const navigate = useNavigate();
  const [idFrontFile, setIdFrontFile] = useState<File | null>(null);
  const [idBackFile, setIdBackFile] = useState<File | null>(null);
  const [selfieFile, setSelfieFile] = useState<File | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CustomerRegisterInput>({
    resolver: zodResolver(customerRegisterSchema),
    defaultValues: { id_type: "national_id", dependants_count: "0" },
  });

  async function onSubmit(values: CustomerRegisterInput) {
    setServerError(null);
    if (!idFrontFile) {
      setServerError("Please attach the front of the ID document");
      return;
    }
    if (!idBackFile) {
      setServerError("Please attach the back of the ID document");
      return;
    }

    const formData = buildMultipartForm(values, {
      id_document: idFrontFile,
      id_document_back: idBackFile,
      selfie_photo: selfieFile,
    });

    try {
      const customer = await apiRequestMultipart<CustomerResponse>("/customers", formData);
      navigate(`/credit/customers/${customer.id}`);
    } catch (err) {
      setServerError(getErrorMessage(err));
    }
  }

  return (
    <AppShell>
      <PageHeader title="New Customer" subtitle="Register a customer's full details in one branch visit" />
      <Card>
        <form className="space-y-6" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div>
            <SectionLabel>Account</SectionLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Email" error={errors.email?.message}>
                <TextInput type="email" {...register("email")} />
              </Field>
              <Field label="Password" error={errors.password?.message}>
                <TextInput type="password" {...register("password")} />
              </Field>
              <Field label="Full name" error={errors.full_name?.message}>
                <TextInput {...register("full_name")} />
              </Field>
            </div>
          </div>

          <div>
            <SectionLabel>Identity</SectionLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="First name" error={errors.first_name?.message}>
                <TextInput {...register("first_name")} />
              </Field>
              <Field label="Middle name (optional)" error={errors.middle_name?.message}>
                <TextInput {...register("middle_name")} />
              </Field>
              <Field label="Last name" error={errors.last_name?.message}>
                <TextInput {...register("last_name")} />
              </Field>
              <Field label="ID type" error={errors.id_type?.message}>
                <Select {...register("id_type")}>
                  <option value="national_id">National ID</option>
                  <option value="passport">Passport</option>
                </Select>
              </Field>
              <Field label="ID / passport number" error={errors.national_id_number?.message}>
                <TextInput {...register("national_id_number")} />
              </Field>
              <Field label="Date of birth" error={errors.date_of_birth?.message}>
                <TextInput type="date" max={maxDateOfBirth()} {...register("date_of_birth")} />
              </Field>
              <Field label="Gender" error={errors.gender?.message}>
                <Select defaultValue="" {...register("gender")}>
                  <option value="" disabled>
                    Select…
                  </option>
                  {GENDER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Nationality" error={errors.nationality?.message}>
                <Select defaultValue="" {...register("nationality")}>
                  <option value="" disabled>
                    Select…
                  </option>
                  {NATIONALITY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Marital status" error={errors.marital_status?.message}>
                <Select defaultValue="" {...register("marital_status")}>
                  <option value="" disabled>
                    Select…
                  </option>
                  {MARITAL_STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Number of dependants" error={errors.dependants_count?.message}>
                <TextInput type="number" min="0" step="1" {...register("dependants_count")} />
              </Field>
            </div>
          </div>

          <div>
            <SectionLabel>Contact</SectionLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Phone number" error={errors.phone_number?.message}>
                <TextInput {...register("phone_number")} />
              </Field>
              <Field label="Alternate phone (optional)" error={errors.phone_number_alt?.message}>
                <TextInput {...register("phone_number_alt")} />
              </Field>
              <Field label="Residential address" error={errors.residential_address?.message}>
                <TextInput {...register("residential_address")} />
              </Field>
            </div>
          </div>

          <div>
            <SectionLabel>Next of kin</SectionLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Full name" error={errors.next_of_kin_name?.message}>
                <TextInput {...register("next_of_kin_name")} />
              </Field>
              <Field label="Relationship" error={errors.next_of_kin_relationship?.message}>
                <Select defaultValue="" {...register("next_of_kin_relationship")}>
                  <option value="" disabled>
                    Select…
                  </option>
                  {NEXT_OF_KIN_RELATIONSHIP_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Phone number" error={errors.next_of_kin_phone?.message}>
                <TextInput {...register("next_of_kin_phone")} />
              </Field>
            </div>
            <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
              Referees can be added from the customer's profile after registration.
            </p>
          </div>

          <div>
            <SectionLabel>Employment</SectionLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Employment status" error={errors.employment_status?.message}>
                <Select defaultValue="" {...register("employment_status")}>
                  <option value="" disabled>
                    Select…
                  </option>
                  {EMPLOYMENT_STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Occupation" error={errors.occupation?.message}>
                <TextInput {...register("occupation")} />
              </Field>
              <Field label="Monthly income (KES)" error={errors.monthly_income?.message}>
                <TextInput type="number" step="0.01" min="0" {...register("monthly_income")} />
              </Field>
            </div>
          </div>

          <div>
            <SectionLabel>Documents</SectionLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                label="Customer photo (optional)"
                accept=".jpg,.jpeg,.png"
                file={selfieFile}
                onChange={setSelfieFile}
                hint="JPG or PNG"
              />
            </div>
          </div>

          {serverError ? <Banner kind="error">{serverError}</Banner> : null}
          <Button type="submit" disabled={isSubmitting} className="w-full">
            {isSubmitting ? "Registering…" : "Register customer"}
          </Button>
        </form>
      </Card>
    </AppShell>
  );
}
