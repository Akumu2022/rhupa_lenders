import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ROLE_HOME } from "../components/nav";

/** Sends a freshly-logged-in user to the one screen their role owns. */
export function DashboardRouter() {
  const { auth } = useAuth();
  if (!auth) return <Navigate to="/login" replace />;
  return <Navigate to={ROLE_HOME[auth.role] ?? "/login"} replace />;
}
