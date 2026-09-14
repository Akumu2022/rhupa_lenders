// Mirrors backend app/schemas/reports.py
export interface ReportResponse {
  start_date: string;
  end_date: string;
  total_disbursed: string;
  total_collected: string;
  total_expenses: string;
  net: string;
  par_percentage: string;
  active_loans: number;
}
