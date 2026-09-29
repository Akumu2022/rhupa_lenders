import type { RepaymentInstallmentResponse } from "../schemas/loan";

/** CLAUDE.md §19 borrower transparency: principal vs interest per
 * installment, not just "amount due". Shared by the customer's own loan
 * schedule, the staff-facing loan detail view, and the loan calculator
 * preview — one rendering of an installment breakdown, not three. */
export function AmortizationTable({ schedule }: { schedule: RepaymentInstallmentResponse[] }) {
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800 dark:text-slate-500">
          <th className="py-2 font-medium">#</th>
          <th className="py-2 font-medium">Due date</th>
          <th className="py-2 font-medium">Principal</th>
          <th className="py-2 font-medium">Interest</th>
          <th className="py-2 font-medium">Amount due</th>
          <th className="py-2 font-medium">Paid</th>
        </tr>
      </thead>
      <tbody>
        {schedule.map((installment) => (
          <tr key={installment.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
            <td className="py-2 text-slate-700 dark:text-slate-300">{installment.installment_number}</td>
            <td className="py-2 text-slate-700 dark:text-slate-300">{installment.due_date}</td>
            <td className="py-2 text-slate-500 dark:text-slate-400">KES {installment.principal_component}</td>
            <td className="py-2 text-slate-500 dark:text-slate-400">KES {installment.interest_component}</td>
            <td className="py-2 font-medium text-slate-900 dark:text-slate-100">KES {installment.amount_due}</td>
            <td className="py-2 text-slate-700 dark:text-slate-300">
              {installment.is_paid ? "Yes" : `KES ${installment.amount_paid}`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
