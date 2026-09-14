import { z } from "zod";
import type { InterestModel, LoanStatus } from "./loan";

// Mirrors backend app/schemas/admin.py
export interface AuditLogResponse {
  id: number;
  actor_email: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  reason: string | null;
  is_platform_action: boolean;
  is_anomaly: boolean;
  created_at: string;
}

export interface AdminLoanResponse {
  id: number;
  customer_full_name: string;
  customer_email: string;
  loan_product_name: string;
  principal: string;
  total_repayable: string;
  // CLAUDE.md §23: 3-way breakdown — principal, base interest
  // (total_repayable - principal), and penalties, never one opaque number.
  penalties_accrued: string;
  outstanding_balance: string;
  status: LoanStatus;
  disbursed_at: string | null;
  created_at: string;
}

export interface AdminLoanProductResponse {
  id: number;
  name: string;
  description: string | null;
  min_amount: string;
  max_amount: string;
  interest_rate: string;
  repayment_period_days: number;
  is_active: boolean;
  // CLAUDE.md §23 — not yet editable from this admin UI, see productUpdateSchema.
  interest_model: InterestModel;
  installment_count: number;
  penalty_type: string;
  penalty_rate: string;
  grace_period_days: number;
  penalty_cap_ratio: string;
}

// CLAUDE.md §25: a company-scoped org unit, not a tenant boundary.
export interface BranchResponse {
  id: number;
  name: string;
  code: string;
  address: string | null;
  manager_id: number | null;
  is_active: boolean;
  created_at: string;
}

export const branchCreateSchema = z.object({
  name: z.string().min(1, "Required"),
  code: z.string().min(1, "Required"),
  address: z.string().optional(),
});
export type BranchCreateInput = z.infer<typeof branchCreateSchema>;

export const productUpdateSchema = z.object({
  name: z.string().min(1, "Required"),
  description: z.string().optional(),
  min_amount: z.string().min(1, "Required"),
  max_amount: z.string().min(1, "Required"),
  interest_rate: z.string().min(1, "Required"),
  repayment_period_days: z.string().min(1, "Required"),
});
export type ProductUpdateInput = z.infer<typeof productUpdateSchema>;

export interface PortfolioTrendPoint {
  date: string;
  disbursed_count: number;
  disbursed_amount: string;
}

export interface PortfolioTrendResponse {
  points: PortfolioTrendPoint[];
}

export interface PortfolioSummaryResponse {
  total_disbursed: string;
  total_collected: string;
  active_borrowers: number;
  active_loans: number;
  outstanding_principal: string;
  par_percentage: string;
  overdue_loans: number;
  defaulted_loans: number;
  loans_disbursed_this_month: number;
  as_of: string;
}
