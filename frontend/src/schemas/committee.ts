import { z } from "zod";

// Mirrors backend app/schemas/committee.py — the committee never escalates
// (it IS the ceiling, CLAUDE.md §26), so only approve/reject are offered.
export const committeeDecisionSchema = z.object({
  decision: z.enum(["approve", "reject"]),
  comments: z.string().min(1, "Comments are required"),
});
export type CommitteeDecisionInput = z.infer<typeof committeeDecisionSchema>;

export interface CommitteeQueueItemResponse {
  id: number;
  customer_full_name: string;
  customer_email: string;
  loan_product_name: string;
  amount_requested: string;
  created_at: string;
  branch_manager_name: string;
  branch_manager_comments: string;
}
