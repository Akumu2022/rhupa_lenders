import { z } from "zod";

// Mirrors backend app/schemas/compliance.py
export interface ComplianceProfileResponse {
  id: number;
  user_id: number;
  kyc_status: "pending" | "verified" | "rejected";
  date_of_birth: string;
  national_id_number: string;
  phone_number: string;
  residential_address: string;
  employment_status: string;
  monthly_income: string;
  occupation: string;
  has_id_document_back: boolean;
  has_selfie: boolean;
  created_at: string;
  reviewed_by: number | null;
  reviewed_at: string | null;
  review_notes: string | null;
  customer_full_name: string;
  customer_email: string;

  // CLAUDE.md §27 (M11) — optional: a pre-M11 or self-signup profile may not
  // have filled all of these in.
  customer_number: string | null;
  first_name: string | null;
  middle_name: string | null;
  last_name: string | null;
  id_type: string | null;
  gender: string | null;
  nationality: string | null;
  marital_status: string | null;
  dependants_count: number | null;
  phone_number_alt: string | null;
  next_of_kin_name: string | null;
  next_of_kin_relationship: string | null;
  next_of_kin_phone: string | null;
}

/** Shared across every KYC-status display (QueuePage, KycPage,
 * CustomerDetailPage, CustomerListPage) — was 4 byte-identical copies. */
export function kycStatusTone(status: "pending" | "verified" | "rejected"): "success" | "danger" | "warning" {
  if (status === "verified") return "success";
  if (status === "rejected") return "danger";
  return "warning";
}

export const kycRejectSchema = z.object({
  reason: z.string().min(1, "A reason is required"),
});
export type KYCRejectInput = z.infer<typeof kycRejectSchema>;
