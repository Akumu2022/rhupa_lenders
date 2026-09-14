import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

interface Props {
  allowedRoles?: string[];
}

/**
 * UX-only guard (CLAUDE.md §4: "the frontend guard is UX only — the backend
 * always enforces"). It exists to route people to the right screen, not to
 * be the security boundary.
 */
export function ProtectedRoute({ allowedRoles }: Props) {
  const { auth } = useAuth();

  if (!auth) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(auth.role)) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
