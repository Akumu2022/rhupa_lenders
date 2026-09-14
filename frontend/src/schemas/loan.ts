// Mirrors backend app/schemas/loan.py
export type InterestModel = "flat" | "reducing_balance" | "daily_accrual";

export interface LoanProductResponse {
  id: number;
  name: string;
  description: string | null;
  min_amount: string;
  max_amount: string;
  interest_rate: string;
  repayment_period_days: number;
  interest_model: InterestModel;
  installment_count: number;
}

export interface LoanApplicationResponse {
  id: number;
  loan_product_id: number;
  amount_requested: string;
  status: "pending" | "approved" | "rejected";
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export type LoanStatus = "approved" | "active" | "overdue" | "defaulted" | "repaid";

export interface RepaymentInstallmentResponse {
  id: number;
  installment_number: number;
  due_date: string;
  amount_due: string;
  amount_paid: string;
  // CLAUDE.md §19: principal vs interest breakdown — principal_component +
  // interest_component === amount_due.
  principal_component: string;
  interest_component: string;
  is_paid: boolean;
}

export interface CustomerLoanResponse {
  id: number;
  loan_product_name: string;
  principal: string;
  interest_rate: string;
  total_repayable: string;
  // CLAUDE.md §23: 3-way breakdown — principal, base interest
  // (total_repayable - principal), and penalties, never one opaque number.
  penalties_accrued: string;
  outstanding_balance: string;
  status: LoanStatus;
  disbursed_at: string | null;
  created_at: string;
  schedule: RepaymentInstallmentResponse[];
}

export interface CustomerCreditSummaryResponse {
  loan_limit: string;
  available_credit: string;
  standing: "good_standing" | "attention_needed";
  loans: CustomerLoanResponse[];
}

export interface RepaymentResponse {
  loan_id: number;
  amount_paid_now: string;
  outstanding_balance: string;
  status: LoanStatus;
}

export interface TransactionResponse {
  id: number;
  loan_id: number;
  type: "disbursement" | "repayment" | "penalty";
  amount: string;
  created_at: string;
}
