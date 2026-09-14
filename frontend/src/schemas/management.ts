// Mirrors backend app/schemas/management.py
export interface BranchRankingItemResponse {
  branch_id: number;
  branch_name: string;
  branch_code: string;
  total_disbursed: string;
  outstanding_principal: string;
  par_percentage: string;
  active_loans: number;
}

export interface StaffPerformanceItemResponse {
  staff_id: number;
  full_name: string;
  role: string;
  branch_name: string | null;
  decisions_made: number;
  approvals: number;
  rejections: number;
}
