import { PortfolioView } from "../../components/PortfolioView";

/** Branch portfolio: same server figures as the dashboard, scoped to the
 * manager's branch server-side. */
export function BranchManagerPortfolioPage() {
  return <PortfolioView subtitle="Your branch's loan book" loansBase="/branch-manager/loans" />;
}
