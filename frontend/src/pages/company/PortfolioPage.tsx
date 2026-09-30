import { PortfolioView } from "../../components/PortfolioView";

/** Company-wide portfolio for the system administrator: the same shared
 * figures every other dashboard uses (GET /analytics/dashboard). */
export function CompanyPortfolioPage() {
  return <PortfolioView subtitle="Your company's loan book: aggregate figures only" />;
}
