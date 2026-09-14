import { z } from "zod";

// Mirrors backend app/schemas/user.py
export const STAFF_ROLES = [
  "credit_officer",
  "branch_manager",
  "loan_vetting_committee",
  "cashier_finance_officer",
  "management",
] as const;

// CLAUDE.md §25: required for credit_officer/branch_manager, optional otherwise.
export const BRANCH_REQUIRED_ROLES = new Set<string>(["credit_officer", "branch_manager"]);

// branch_id comes off an HTML <select> as a string; kept as a string here and
// converted to a number (or omitted) right before the API call — see
// UsersPage.tsx's onSubmit.
export const staffCreateSchema = z
  .object({
    email: z.string().email("Enter a valid email"),
    password: z.string().min(8, "At least 8 characters"),
    full_name: z.string().min(1, "Name is required"),
    role: z.enum(STAFF_ROLES),
    branch_id: z.string().optional(),
  })
  .refine((data) => !BRANCH_REQUIRED_ROLES.has(data.role) || !!data.branch_id, {
    message: "Branch is required for this role",
    path: ["branch_id"],
  });
export type StaffCreateInput = z.infer<typeof staffCreateSchema>;

export interface UserResponse {
  id: number;
  email: string;
  full_name: string;
  role: string;
  company_id: number | null;
  branch_id: number | null;
  is_active: boolean;
}
