// Mirrors backend app/schemas/credit.py
import type { LoanStatus } from "./loan";

export interface CreditApplicationResponse {
  id: number;
  customer_full_name: string;
  customer_email: string;
  loan_product_name: string;
  amount_requested: string;
  status: "pending" | "approved" | "rejected";
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
  // null until approved AND a Loan exists for it — distinguishes "approved,
  // awaiting disbursement" from "disbursed" (and later overdue/defaulted/repaid).
  loan_status: LoanStatus | null;
}

/** One unified lifecycle label per application, so "approved" never has to
 * silently mean two different things (awaiting disbursement vs. already
 * disbursed) on screen. */
export function describeApplicationLifecycle(
  application: CreditApplicationResponse,
): { label: string; tone: "success" | "danger" | "warning" | "info" | "neutral" } {
  if (application.status === "pending") return { label: "Pending review", tone: "warning" };
  if (application.status === "rejected") return { label: "Declined", tone: "danger" };

  switch (application.loan_status) {
    case "approved":
      return { label: "Awaiting disbursement", tone: "info" };
    case "active":
      return { label: "Disbursed", tone: "success" };
    case "overdue":
      return { label: "Disbursed · Overdue", tone: "danger" };
    case "defaulted":
      return { label: "Disbursed · Defaulted", tone: "danger" };
    case "repaid":
      return { label: "Disbursed · Repaid", tone: "success" };
    default:
      return { label: "Approved", tone: "success" };
  }
}

export interface LoanResponse {
  id: number;
  application_id: number;
  principal: string;
  interest_rate: string;
  total_repayable: string;
  // CLAUDE.md §23: 3-way breakdown — principal, base interest
  // (total_repayable - principal), and penalties, never one opaque number.
  penalties_accrued: string;
  outstanding_balance: string;
  status: LoanStatus;
  disbursed_at?: string | null;
}

export interface LoanApprovalResponse {
  application: CreditApplicationResponse;
  loan: LoanResponse;
  repayment_due_date: string;
  repayment_amount_due: string;
}

export interface DisbursementResponse {
  loan: LoanResponse;
}

export interface PendingDisbursementResponse {
  id: number;
  customer_full_name: string;
  customer_email: string;
  loan_product_name: string;
  principal: string;
  total_repayable: string;
  created_at: string;
}

export interface LoanDefaultRequest {
  reason: string;
}

export interface CollectionsQueueItemResponse {
  id: number;
  customer_full_name: string;
  customer_email: string;
  loan_product_name: string;
  outstanding_balance: string;
  status: LoanStatus;
  earliest_overdue_due_date: string;
  days_overdue: number;
}
