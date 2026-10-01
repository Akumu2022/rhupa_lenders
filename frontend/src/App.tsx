import { Navigate, Route, Routes } from "react-router-dom";
import { TopProgressBar } from "./components/TopProgressBar";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { CustomerSignupPage } from "./pages/customer/SignupPage";
import { DashboardRouter } from "./pages/DashboardRouter";
import { PlatformDashboardPage } from "./pages/platform/DashboardPage";
import { PlatformCompaniesPage } from "./pages/platform/CompaniesPage";
import { CompanyAdminDashboardPage } from "./pages/company/DashboardPage";
import { CompanyAdminUsersPage } from "./pages/company/UsersPage";
import { StaffDetailPage } from "./pages/company/StaffDetailPage";
import { CompanyApplicationsPage } from "./pages/company/ApplicationsPage";
import { CompanyKycPage } from "./pages/company/KycPage";
import { CompanyLoansPage } from "./pages/company/LoansPage";
import { CompanyLoanCalculatorPage } from "./pages/company/LoanCalculatorPage";
import { CompanyProductsPage } from "./pages/company/ProductsPage";
import { CompanyPortfolioPage } from "./pages/company/PortfolioPage";
import { CompanyAuditLogPage } from "./pages/company/AuditLogPage";
import { CompanyProfilePage } from "./pages/company/CompanyProfilePage";
import { CompanyBranchesPage } from "./pages/company/BranchesPage";
import { ComplianceDashboardPage } from "./pages/compliance/DashboardPage";
import { ComplianceQueuePage } from "./pages/compliance/QueuePage";
import { CreditDashboardPage } from "./pages/credit/DashboardPage";
import { CreditApplicationsPage } from "./pages/credit/ApplicationsPage";
import { CollectionsPage } from "./pages/credit/CollectionsPage";
import { RegisterCustomerPage } from "./pages/credit/RegisterCustomerPage";
import { CustomerListPage } from "./pages/customers/CustomerListPage";
import { CustomerDetailPage } from "./pages/customers/CustomerDetailPage";
import { BranchManagerDashboardPage } from "./pages/branch-manager/DashboardPage";
import { BranchManagerApplicationsPage } from "./pages/branch-manager/ApplicationsPage";
import { BranchManagerStaffPage } from "./pages/branch-manager/StaffPage";
import { BranchManagerPortfolioPage } from "./pages/branch-manager/PortfolioPage";
import { BranchManagerCollectionsPage } from "./pages/branch-manager/CollectionsPage";
import { CommitteeDashboardPage } from "./pages/committee/DashboardPage";
import { CommitteeQueuePage } from "./pages/committee/QueuePage";
import { CommitteeDecisionsPage } from "./pages/committee/DecisionsPage";
import { FinanceDashboardPage } from "./pages/finance/DashboardPage";
import { FinanceDisbursementsPage } from "./pages/finance/DisbursementsPage";
import { FinanceFinancialsPage } from "./pages/finance/FinancialsPage";
import { FinanceReportsPage } from "./pages/finance/ReportsPage";
import { ManagementDashboardPage } from "./pages/management/DashboardPage";
import { ManagementReportsPage } from "./pages/management/ReportsPage";
import { ManagementBranchRankingPage } from "./pages/management/BranchRankingPage";
import { ManagementStaffPerformancePage } from "./pages/management/StaffPerformancePage";
import { CustomerDashboardPage } from "./pages/customer/DashboardPage";
import { CustomerLoansPage } from "./pages/customer/LoansPage";
import { CustomerApplyPage } from "./pages/customer/ApplyPage";
import { CustomerRepaymentsPage } from "./pages/customer/RepaymentsPage";
import { CustomerProfilePage } from "./pages/customer/ProfilePage";
import { SecurityPage } from "./pages/SecurityPage";

function App() {
  return (
    <>
      <TopProgressBar />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<CustomerSignupPage />} />
      <Route path="/apply/:code" element={<CustomerSignupPage />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<DashboardRouter />} />
      </Route>

      {/* CLAUDE.md §4/MFA: every staff role, never customers (they can't
          enroll — see app/routers/mfa.py). */}
      <Route
        element={
          <ProtectedRoute
            allowedRoles={[
              "super_admin",
              "system_administrator",
              "credit_officer",
              "branch_manager",
              "loan_vetting_committee",
              "cashier_finance_officer",
              "management",
            ]}
          />
        }
      >
        <Route path="/security" element={<SecurityPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["super_admin"]} />}>
        <Route path="/platform" element={<PlatformDashboardPage />} />
        <Route path="/platform/companies" element={<PlatformCompaniesPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["system_administrator"]} />}>
        <Route path="/admin" element={<CompanyAdminDashboardPage />} />
        <Route path="/admin/users" element={<CompanyAdminUsersPage />} />
        <Route path="/admin/users/:userId" element={<StaffDetailPage />} />
        <Route path="/admin/branches" element={<CompanyBranchesPage />} />
        <Route path="/admin/applications" element={<CompanyApplicationsPage />} />
        <Route path="/admin/kyc" element={<CompanyKycPage />} />
        <Route path="/admin/loans" element={<CompanyLoansPage />} />
        <Route path="/admin/loans/calculator" element={<CompanyLoanCalculatorPage />} />
        <Route path="/admin/collections" element={<CollectionsPage />} />
        <Route path="/admin/products" element={<CompanyProductsPage />} />
        <Route path="/admin/portfolio" element={<CompanyPortfolioPage />} />
        <Route path="/admin/audit-log" element={<CompanyAuditLogPage />} />
        <Route path="/admin/company-profile" element={<CompanyProfilePage />} />
        <Route path="/admin/customers" element={<CustomerListPage />} />
        <Route path="/admin/customers/:customerId" element={<CustomerDetailPage />} />
      </Route>

      {/* CLAUDE.md §3/M10: compliance_officer retired — credit_officer now
          owns KYC capture/verification, so these routes are credit_officer-gated. */}
      <Route element={<ProtectedRoute allowedRoles={["credit_officer"]} />}>
        <Route path="/compliance" element={<ComplianceDashboardPage />} />
        <Route path="/compliance/queue" element={<ComplianceQueuePage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["credit_officer"]} />}>
        <Route path="/credit" element={<CreditDashboardPage />} />
        <Route path="/credit/customers/new" element={<RegisterCustomerPage />} />
        <Route path="/credit/customers/:customerId" element={<CustomerDetailPage />} />
        <Route path="/credit/customers" element={<CustomerListPage />} />
        <Route path="/credit/applications" element={<CreditApplicationsPage />} />
        <Route path="/credit/collections" element={<CollectionsPage />} />
        <Route path="/credit/portfolio" element={<CreditApplicationsPage mode="mine" />} />
        {/* My Decisions retired: credit officers stopped deciding in M13 (CLAUDE.md §26). */}
        <Route path="/credit/decisions" element={<Navigate to="/credit/portfolio" replace />} />
      </Route>

      {/* CLAUDE.md §14 M13/M14/M17/M18: multi-stage approval chain,
          disbursement handoff, and financial/management reporting. */}
      <Route element={<ProtectedRoute allowedRoles={["branch_manager"]} />}>
        <Route path="/branch-manager" element={<BranchManagerDashboardPage />} />
        <Route path="/branch-manager/applications" element={<BranchManagerApplicationsPage />} />
        <Route path="/branch-manager/staff" element={<BranchManagerStaffPage />} />
        <Route path="/branch-manager/portfolio" element={<BranchManagerPortfolioPage />} />
        <Route
          path="/branch-manager/loans"
          element={
            <CreditApplicationsPage
              title="Loans"
              subtitle="Every application and loan in your branch, from submission to repayment"
              canEditGuarantors={false}
            />
          }
        />
        <Route path="/branch-manager/collections" element={<BranchManagerCollectionsPage />} />
        <Route path="/branch-manager/customers" element={<CustomerListPage />} />
        <Route path="/branch-manager/customers/:customerId" element={<CustomerDetailPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["loan_vetting_committee"]} />}>
        <Route path="/committee" element={<CommitteeDashboardPage />} />
        <Route path="/committee/queue" element={<CommitteeQueuePage />} />
        <Route path="/committee/decisions" element={<CommitteeDecisionsPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["cashier_finance_officer"]} />}>
        <Route path="/finance" element={<FinanceDashboardPage />} />
        <Route path="/finance/disbursements" element={<FinanceDisbursementsPage />} />
        <Route
          path="/finance/loans"
          element={
            <CreditApplicationsPage
              title="Loans"
              subtitle="Every application and loan in the company, from submission to repayment"
              canEditGuarantors={false}
            />
          }
        />
        <Route path="/finance/financials" element={<FinanceFinancialsPage />} />
        <Route path="/finance/reports" element={<FinanceReportsPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["management"]} />}>
        <Route path="/management" element={<ManagementDashboardPage />} />
        <Route path="/management/reports" element={<ManagementReportsPage />} />
        <Route path="/management/branch-ranking" element={<ManagementBranchRankingPage />} />
        <Route path="/management/staff-performance" element={<ManagementStaffPerformancePage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["customer"]} />}>
        <Route path="/customer" element={<CustomerDashboardPage />} />
        <Route path="/customer/loans" element={<CustomerLoansPage />} />
        <Route path="/customer/apply" element={<CustomerApplyPage />} />
        <Route path="/customer/repayments" element={<CustomerRepaymentsPage />} />
        <Route path="/customer/profile" element={<CustomerProfilePage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default App;
