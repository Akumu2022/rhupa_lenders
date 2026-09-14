import { z } from "zod";

// Mirrors backend app/models/expense_entry.py::ExpenseCategory
export const EXPENSE_CATEGORIES = [
  "salaries",
  "rent",
  "transport",
  "communications",
  "administration",
  "other",
] as const;

export const EXPENSE_CATEGORY_LABELS: Record<string, string> = {
  salaries: "Salaries",
  rent: "Rent",
  transport: "Transport",
  communications: "Communications",
  administration: "Administration",
  other: "Other",
};

// Mirrors backend app/schemas/finance.py
export const expenseCreateSchema = z.object({
  category: z.enum(EXPENSE_CATEGORIES),
  amount: z.string().min(1, "Amount is required"),
  description: z.string().optional(),
});
export type ExpenseCreateInput = z.infer<typeof expenseCreateSchema>;

export interface ExpenseResponse {
  id: number;
  category: string;
  amount: string;
  description: string | null;
  branch_id: number | null;
  created_by_name: string;
  created_at: string;
}

export interface FinancialsResponse {
  period_start: string;
  total_repayment_income: string;
  total_penalty_income: string;
  total_disbursed: string;
  total_expenses: string;
  net: string;
  recent_expenses: ExpenseResponse[];
}
