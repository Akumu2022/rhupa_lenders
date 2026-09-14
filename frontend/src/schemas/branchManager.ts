import { z } from "zod";

// Mirrors backend app/schemas/branch_manager.py
export const applicationDecisionSchema = z.object({
  decision: z.enum(["approve", "reject", "escalate"]),
  comments: z.string().min(1, "Comments are required"),
});
export type ApplicationDecisionInput = z.infer<typeof applicationDecisionSchema>;

export interface BranchQueueItemResponse {
  id: number;
  customer_full_name: string;
  customer_email: string;
  loan_product_name: string;
  amount_requested: string;
  created_at: string;
  effective_limit: string;
  over_limit: boolean;
}
