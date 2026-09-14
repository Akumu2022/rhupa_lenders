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
import { CompanyApplicationsPage } from "./pages/company/ApplicationsPage";
import { CompanyKycPage } from "./pages/company/KycPage";
import { CompanyLoansPage } from "./pages/company/LoansPage";
import { CompanyProductsPage } from "./pages/company/ProductsPage";
import { CompanyPortfolioPage } from "./pages/company/PortfolioPage";
import { CompanyAuditLogPage } from "./pages/company/AuditLogPage";
import { CompanyProfilePage } from "./pages/company/CompanyProfilePage";
import { CompanyBranchesPage } from "./pages/company/BranchesPage";
import { ComplianceDashboardPage } from "./pages/compliance/DashboardPage";
import { ComplianceQueuePage } from "./pages/compliance/QueuePage";
import { CreditDashboardPage } from "./pages/credit/DashboardPage";
import { CreditApplicationsPage } from "./pages/credit/ApplicationsPage";
import { CreditDecisionsPage } from "./pages/credit/DecisionsPage";
import { CollectionsPage } from "./pages/credit/CollectionsPage";
import { RegisterCustomerPage } from "./pages/credit/RegisterCustomerPage";
import { CustomerListPage } from "./pages/credit/CustomerListPage";
import { CustomerDetailPage } from "./pages/credit/CustomerDetailPage";
import { BranchManagerDashboardPage } from "./pages/branch-manager/DashboardPage";
import { CommitteeDashboardPage } from "./pages/committee/DashboardPage";
import { FinanceDashboardPage } from "./pages/finance/DashboardPage";
import { ManagementDashboardPage } from "./pages/management/DashboardPage";
import { CustomerDashboardPage } from "./pages/customer/DashboardPage";
import { CustomerLoansPage } from "./pages/customer/LoansPage";
import { CustomerApplyPage } from "./pages/customer/ApplyPage";
import { CustomerRepaymentsPage } from "./pages/customer/RepaymentsPage";
import { CustomerProfilePage } from "./pages/customer/ProfilePage";

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

      <Route element={<ProtectedRoute allowedRoles={["super_admin"]} />}>
        <Route path="/platform" element={<PlatformDashboardPage />} />
        <Route path="/platform/companies" element={<PlatformCompaniesPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["system_administrator"]} />}>
        <Route path="/admin" element={<CompanyAdminDashboardPage />} />
        <Route path="/admin/users" element={<CompanyAdminUsersPage />} />
        <Route path="/admin/branches" element={<CompanyBranchesPage />} />
        <Route path="/admin/applications" element={<CompanyApplicationsPage />} />
        <Route path="/admin/kyc" element={<CompanyKycPage />} />
        <Route path="/admin/loans" element={<CompanyLoansPage />} />
        <Route path="/admin/collections" element={<CollectionsPage />} />
        <Route path="/admin/products" element={<CompanyProductsPage />} />
        <Route path="/admin/portfolio" element={<CompanyPortfolioPage />} />
        <Route path="/admin/audit-log" element={<CompanyAuditLogPage />} />
        <Route path="/admin/company-profile" element={<CompanyProfilePage />} />
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
        <Route path="/credit/decisions" element={<CreditDecisionsPage />} />
      </Route>

      {/* CLAUDE.md §14 M10: minimal placeholder dashboards — full builds land
          in M15/M17/M18/M19 once their data endpoints exist (§18: "not built
          = not faked"). */}
      <Route element={<ProtectedRoute allowedRoles={["branch_manager"]} />}>
        <Route path="/branch-manager" element={<BranchManagerDashboardPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["loan_vetting_committee"]} />}>
        <Route path="/committee" element={<CommitteeDashboardPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["cashier_finance_officer"]} />}>
        <Route path="/finance" element={<FinanceDashboardPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["management"]} />}>
        <Route path="/management" element={<ManagementDashboardPage />} />
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
