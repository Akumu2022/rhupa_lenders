import { useSearchParams } from "react-router-dom";
import { BranchLoanDashboard } from "../../components/BranchLoanDashboard";

/** Credit officer dashboard: scoped to the officer's branch server-side, or
 * to applications they prepared ("My customers only"). The officer prepares;
 * decisions happen upstream (CLAUDE.md §8/§26), so there is no "my
 * decisions" figure here. */
export function CreditDashboardPage() {
  const [params, setParams] = useSearchParams();
  const mine = params.get("mine") === "1";

  function toggleMine() {
    const p = new URLSearchParams(params);
    if (mine) p.delete("mine");
    else p.set("mine", "1");
    setParams(p, { replace: true });
  }

  return (
    <BranchLoanDashboard
      subtitle={mine ? "Applications you prepared" : "Your branch — applications, loans, and what's due"}
      listBase={mine ? "/credit/portfolio" : "/credit/applications"}
      mine={mine}
      headerExtras={
        <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
          <input type="checkbox" checked={mine} onChange={toggleMine} className="rounded" />
          My customers only
        </label>
      }
    />
  );
}
