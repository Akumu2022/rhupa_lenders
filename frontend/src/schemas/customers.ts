import { z } from "zod";

// Fixed choice lists for the customer registration form's categorical
// fields — the backend stores each as a plain string (app/models/profile.py
// has no DB-level enum for these), so this is a frontend-only constraint:
// present a closed set instead of free text, rather than a data-model
// change. Values are the exact strings sent to and stored by the backend.
export const GENDER_OPTIONS = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
] as const;

export const NATIONALITY_OPTIONS = [
  { value: "Kenya", label: "Kenya" },
  { value: "Uganda", label: "Uganda" },
  { value: "Tanzania", label: "Tanzania" },
] as const;

export const MARITAL_STATUS_OPTIONS = [
  { value: "married", label: "Married" },
  { value: "single", label: "Single" },
  { value: "divorced", label: "Divorced" },
] as const;

export const NEXT_OF_KIN_RELATIONSHIP_OPTIONS = [
  { value: "father", label: "Father" },
  { value: "mother", label: "Mother" },
  { value: "brother", label: "Brother" },
  { value: "sister", label: "Sister" },
  { value: "spouse", label: "Spouse" },
  { value: "child", label: "Child" },
] as const;

export const EMPLOYMENT_STATUS_OPTIONS = [
  { value: "employed", label: "Employed" },
  { value: "unemployed", label: "Unemployed" },
  { value: "self_employed", label: "Self Employed" },
] as const;

const MIN_CUSTOMER_AGE_YEARS = 18;

function isAtLeastYearsOld(dateString: string, years: number): boolean {
  const dob = new Date(dateString);
  if (Number.isNaN(dob.getTime())) return false;
  const today = new Date();
  const cutoff = new Date(today.getFullYear() - years, today.getMonth(), today.getDate());
  return dob <= cutoff;
}

// Mirrors backend app/schemas/customers.py
export const customerRegisterSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
  full_name: z.string().min(1, "Required"),

  first_name: z.string().min(1, "Required"),
  middle_name: z.string().optional(),
  last_name: z.string().min(1, "Required"),
  id_type: z.enum(["national_id", "passport"]),
  national_id_number: z.string().min(1, "Required"),
  date_of_birth: z
    .string()
    .min(1, "Required")
    .refine((v) => isAtLeastYearsOld(v, MIN_CUSTOMER_AGE_YEARS), {
      message: "Customer must be at least 18 years old",
    }),
  gender: z.enum(["male", "female"], { message: "Required" }),
  nationality: z.enum(["Kenya", "Uganda", "Tanzania"], { message: "Required" }),
  marital_status: z.enum(["married", "single", "divorced"], { message: "Required" }),
  dependants_count: z.string().min(1, "Required"),

  phone_number: z.string().min(1, "Required"),
  phone_number_alt: z.string().optional(),
  residential_address: z.string().min(1, "Required"),

  employment_status: z.enum(["employed", "unemployed", "self_employed"], { message: "Required" }),
  occupation: z.string().min(1, "Required"),
  monthly_income: z.string().min(1, "Required"),

  next_of_kin_name: z.string().min(1, "Required"),
  next_of_kin_relationship: z.enum(["father", "mother", "brother", "sister", "spouse", "child"], {
    message: "Required",
  }),
  next_of_kin_phone: z.string().min(1, "Required"),
});
export type CustomerRegisterInput = z.infer<typeof customerRegisterSchema>;

export interface CustomerResponse {
  id: number;
  profile_id: number;
  customer_number: string | null;
  full_name: string;
  email: string;
  branch_id: number | null;
  kyc_status: "pending" | "verified" | "rejected";
  created_at: string;
}

export const refereeInputSchema = z.object({
  full_name: z.string().min(1, "Required"),
  phone_number: z.string().min(1, "Required"),
  relationship: z.string().optional(),
  address: z.string().optional(),
});
export type RefereeInputForm = z.infer<typeof refereeInputSchema>;

export interface RefereeResponse {
  id: number;
  profile_id: number;
  full_name: string;
  phone_number: string;
  relationship: string | null;
  address: string | null;
  created_at: string;
}

export const businessAssessmentSchema = z.object({
  business_name: z.string().min(1, "Required"),
  business_type: z.string().min(1, "Required"),
  ownership: z.string().min(1, "Required"),
  physical_location: z.string().min(1, "Required"),
  years_in_operation: z.string().min(1, "Required"),
  sales_frequency: z.enum(["daily", "weekly", "monthly"]),
  total_income: z.string().min(1, "Required"),
  total_expenses: z.string().min(1, "Required"),
  reported_profit: z.string().optional(),
  stock_value: z.string().optional(),
  existing_loans_amount: z.string().optional(),
  other_lenders: z.string().optional(),
  bank_mpesa_turnover: z.string().optional(),
  business_assets_value: z.string().optional(),
  cash_flow_notes: z.string().optional(),
  existing_debt_obligations: z.string().optional(),
});
export type BusinessAssessmentInput = z.infer<typeof businessAssessmentSchema>;

export interface BusinessAssessmentResponse {
  id: number;
  profile_id: number;
  business_name: string;
  business_type: string;
  ownership: string;
  physical_location: string;
  years_in_operation: number;
  sales_frequency: string;
  total_income: string;
  total_expenses: string;
  reported_profit: string | null;
  stock_value: string | null;
  existing_loans_amount: string | null;
  other_lenders: string | null;
  bank_mpesa_turnover: string | null;
  business_assets_value: string | null;
  cash_flow_notes: string | null;
  existing_debt_obligations: string;
  net_income: string;
  debt_service_capacity: string;
  created_at: string;
  updated_at: string;
}
