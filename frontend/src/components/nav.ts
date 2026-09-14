import type { IconName } from "./icons";

export interface NavItem {
  label: string;
  path: string;
  icon: IconName;
  /** Not backed by a shipped milestone yet — shown greyed out with a "Soon" badge (§18: not built = not faked). */
  soon?: boolean;
}

export const ROLE_HOME: Record<string, string> = {
  super_admin: "/platform",
  system_administrator: "/admin",
  credit_officer: "/credit",
  branch_manager: "/branch-manager",
  loan_vetting_committee: "/committee",
  cashier_finance_officer: "/finance",
  management: "/management",
  customer: "/customer",
};

export const ROLE_LABELS: Record<string, string> = {
  super_admin: "Platform Super Admin",
  system_administrator: "System Administrator",
  credit_officer: "Credit Officer",
  branch_manager: "Branch Manager",
  loan_vetting_committee: "Loan Vetting Committee",
  cashier_finance_officer: "Cashier / Finance Officer",
  management: "Management",
  customer: "Customer",
};

export const NAV_BY_ROLE: Record<string, NavItem[]> = {
  customer: [
    { label: "Dashboard", path: "/customer", icon: "dashboard" },
    { label: "My Loans", path: "/customer/loans", icon: "wallet" },
    { label: "Apply", path: "/customer/apply", icon: "plusCircle" },
    { label: "Repayments", path: "/customer/repayments", icon: "creditCard" },
    { label: "Profile", path: "/customer/profile", icon: "user" },
  ],
  // CLAUDE.md §3/M10: compliance_officer retired — credit_officer now owns
  // customer registration, KYC capture/verification, and appraisal.
  credit_officer: [
    { label: "Dashboard", path: "/credit", icon: "dashboard" },
    { label: "New Customer", path: "/credit/customers/new", icon: "plusCircle" },
    { label: "Customer List", path: "/credit/customers", icon: "users" },
    { label: "KYC Queue", path: "/compliance/queue", icon: "clipboardList" },
    { label: "Applications", path: "/credit/applications", icon: "documentText" },
    { label: "Collections", path: "/credit/collections", icon: "archiveBox" },
    { label: "My Decisions", path: "/credit/decisions", icon: "checkCircle" },
  ],
  branch_manager: [
    { label: "Dashboard", path: "/branch-manager", icon: "dashboard" },
    { label: "Staff", path: "/branch-manager/staff", icon: "users", soon: true },
    { label: "Applications", path: "/branch-manager/applications", icon: "documentText", soon: true },
    { label: "Portfolio", path: "/branch-manager/portfolio", icon: "chartBar", soon: true },
    { label: "Collections", path: "/branch-manager/collections", icon: "archiveBox", soon: true },
  ],
  loan_vetting_committee: [
    { label: "Dashboard", path: "/committee", icon: "dashboard" },
    { label: "Committee Queue", path: "/committee/queue", icon: "documentText", soon: true },
    { label: "My Decisions", path: "/committee/decisions", icon: "checkCircle", soon: true },
  ],
  cashier_finance_officer: [
    { label: "Dashboard", path: "/finance", icon: "dashboard" },
    { label: "Disbursements", path: "/finance/disbursements", icon: "banknotes", soon: true },
    { label: "Financials", path: "/finance/financials", icon: "chartBar", soon: true },
    { label: "Reports", path: "/finance/reports", icon: "archiveBox", soon: true },
  ],
  management: [
    { label: "Dashboard", path: "/management", icon: "dashboard" },
    { label: "Reports", path: "/management/reports", icon: "archiveBox", soon: true },
    { label: "Branch Ranking", path: "/management/branch-ranking", icon: "chartBar", soon: true },
    { label: "Staff Performance", path: "/management/staff-performance", icon: "users", soon: true },
  ],
  system_administrator: [
    { label: "Dashboard", path: "/admin", icon: "dashboard" },
    { label: "Users", path: "/admin/users", icon: "users" },
    { label: "Branches", path: "/admin/branches", icon: "buildingOffice" },
    { label: "Applications", path: "/admin/applications", icon: "documentText" },
    { label: "KYC", path: "/admin/kyc", icon: "clipboardList" },
    { label: "Loans", path: "/admin/loans", icon: "banknotes" },
    { label: "Collections", path: "/admin/collections", icon: "archiveBox" },
    { label: "Products", path: "/admin/products", icon: "cube" },
    { label: "Portfolio", path: "/admin/portfolio", icon: "chartBar" },
    { label: "Audit Log", path: "/admin/audit-log", icon: "archiveBox" },
    { label: "Company Profile", path: "/admin/company-profile", icon: "buildingOffice" },
  ],
  super_admin: [
    { label: "Dashboard", path: "/platform", icon: "dashboard" },
    { label: "Companies", path: "/platform/companies", icon: "buildingOffice" },
  ],
};
