import { z } from "zod";

// Mirrors backend app/schemas/profile.py
export interface ProfileResponse {
  id: number;
  kyc_status: "pending" | "verified" | "rejected";
  date_of_birth: string;
  national_id_number: string;
  phone_number: string;
  residential_address: string;
  employment_status: string;
  monthly_income: string;
  occupation: string;
  review_notes: string | null;
  reviewed_at: string | null;

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

export const profileSubmitSchema = z.object({
  date_of_birth: z.string().min(1, "Required"),
  national_id_number: z.string().min(1, "Required"),
  phone_number: z.string().min(1, "Required"),
  residential_address: z.string().min(1, "Required"),
  employment_status: z.string().min(1, "Required"),
  monthly_income: z.string().min(1, "Required"),
  occupation: z.string().min(1, "Required"),
});
export type ProfileSubmitInput = z.infer<typeof profileSubmitSchema>;
