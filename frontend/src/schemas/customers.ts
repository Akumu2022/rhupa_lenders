import { z } from "zod";

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
  date_of_birth: z.string().min(1, "Required"),
  gender: z.string().min(1, "Required"),
  nationality: z.string().min(1, "Required"),
  marital_status: z.string().min(1, "Required"),
  dependants_count: z.string().min(1, "Required"),

  phone_number: z.string().min(1, "Required"),
  phone_number_alt: z.string().optional(),
  residential_address: z.string().min(1, "Required"),

  employment_status: z.string().min(1, "Required"),
  occupation: z.string().min(1, "Required"),
  monthly_income: z.string().min(1, "Required"),

  next_of_kin_name: z.string().min(1, "Required"),
  next_of_kin_relationship: z.string().min(1, "Required"),
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
