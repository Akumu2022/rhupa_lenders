import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest } from "../api/client";
import type { ReportResponse } from "../schemas/reports";
import { Banner, Card, Field, LoadingRow, SectionLabel, StatCard, TextInput } from "./ui";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

/** CLAUDE.md §30 (M18): one parameterized date-range report view shared by
 * cashier_finance_officer and management — same "one dispatcher, selected
 * by a parameter" philosophy §23 already uses for interest models, applied
 * here on the frontend too instead of building two near-identical pages. */
export function ReportsView({ endpoint, queryKeyPrefix }: { endpoint: string; queryKeyPrefix: string }) {
  const [startDate, setStartDate] = useState(isoDaysAgo(30));
  const [endDate, setEndDate] = useState(isoDaysAgo(0));

  const reportQuery = useQuery({
    queryKey: [queryKeyPrefix, "reports", startDate, endDate],
    queryFn: () => apiRequest<ReportResponse>(`${endpoint}?start_date=${startDate}&end_date=${endDate}`),
    enabled: startDate <= endDate,
  });

  return (
    <div className="space-y-4">
      <Card>
        <SectionLabel>Date range</SectionLabel>
        <div className="flex flex-wrap items-end gap-4">
          <Field label="From">
            <TextInput type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </Field>
          <Field label="To">
            <TextInput type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </Field>
        </div>
        {startDate > endDate ? <Banner kind="error">Start date must not be after end date</Banner> : null}
      </Card>

      {reportQuery.isLoading ? <LoadingRow /> : null}
      {reportQuery.isError ? <Banner kind="error">Could not load the report for this range</Banner> : null}

      {reportQuery.data ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard label="Disbursed" value={`KES ${reportQuery.data.total_disbursed}`} tone="brand" />
          <StatCard label="Collected" value={`KES ${reportQuery.data.total_collected}`} tone="success" />
          <StatCard label="Expenses" value={`KES ${reportQuery.data.total_expenses}`} tone="neutral" />
          <StatCard
            label="Net"
            value={`KES ${reportQuery.data.net}`}
            tone={Number(reportQuery.data.net) >= 0 ? "success" : "danger"}
          />
          <StatCard
            label="Portfolio at risk"
            value={`${reportQuery.data.par_percentage}%`}
            tone={Number(reportQuery.data.par_percentage) > 0 ? "danger" : "success"}
          />
          <StatCard label="Active loans" value={reportQuery.data.active_loans} tone="neutral" />
        </div>
      ) : null}
    </div>
  );
}
