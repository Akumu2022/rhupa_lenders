import { z } from "zod";

// Mirrors backend app/schemas/guarantor.py
export const guarantorInputSchema = z.object({
  full_name: z.string().min(1, "Required"),
  id_number: z.string().min(1, "Required"),
  phone_number: z.string().min(1, "Required"),
  occupation: z.string().optional(),
  residence: z.string().optional(),
  relationship: z.string().optional(),
  guaranteed_amount: z.string().min(1, "Required"),
  consent: z.boolean().optional(),
});
export type GuarantorInputForm = z.infer<typeof guarantorInputSchema>;

export type GuarantorVerificationStatus = "pending" | "verified" | "rejected";

export interface GuarantorResponse {
  id: number;
  application_id: number;
  full_name: string;
  id_number: string;
  phone_number: string;
  occupation: string | null;
  residence: string | null;
  relationship: string | null;
  guaranteed_amount: string;
  consent: boolean;
  verification_status: GuarantorVerificationStatus;
  verified_by: number | null;
  verified_at: string | null;
  created_at: string;
}

export const securityInputSchema = z.object({
  description: z.string().min(1, "Required"),
  estimated_value: z.string().min(1, "Required"),
});
export type SecurityInputForm = z.infer<typeof securityInputSchema>;

export interface SecurityResponse {
  id: number;
  application_id: number;
  description: string;
  estimated_value: string;
  document_path: string | null;
  created_at: string;
}

export function guarantorStatusTone(status: GuarantorVerificationStatus): "success" | "warning" | "danger" {
  if (status === "verified") return "success";
  if (status === "rejected") return "danger";
  return "warning";
}
