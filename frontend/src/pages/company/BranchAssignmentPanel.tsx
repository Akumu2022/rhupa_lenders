import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { useToast } from "../../components/toast";
import { Badge, Banner, Button, Card, EmptyState, SectionLabel, Select } from "../../components/ui";
import type { BranchResponse } from "../../schemas/admin";

// Mirrors backend app/schemas/branch_assignment.py.
interface UnassignedUser {
  id: number;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
}
interface BranchAssignmentOverview {
  staff_missing_branch: UnassignedUser[];
  customers_missing_branch: UnassignedUser[];
  applications_without_branch: number;
}
interface AssignBranchResponse {
  user_id: number;
  branch_id: number | null;
  rerouted_application_ids: number[];
}

const ROLE_LABEL: Record<string, string> = {
  credit_officer: "Credit officer",
  branch_manager: "Branch manager",
  customer: "Customer",
};

/** People who should have a branch but don't: accounts from before branches
 * existed, and customers who signed up on the plain (non-branch) link. */
export function NeedsBranchPanel({ branches }: { branches: BranchResponse[] }) {
  const query = useQuery({
    queryKey: ["admin", "branch-assignment"],
    queryFn: () => apiRequest<BranchAssignmentOverview>("/admin/branch-assignment"),
  });
  const data = query.data;
  const activeBranches = branches.filter((b) => b.is_active);
  const total = data ? data.staff_missing_branch.length + data.customers_missing_branch.length : 0;

  if (query.isLoading || !data) return null;

  return (
    <Card className="mb-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <SectionLabel>Needs a branch</SectionLabel>
        {total > 0 ? <Badge tone="warning">{total} to assign</Badge> : <Badge tone="success">All assigned</Badge>}
      </div>
      {data.applications_without_branch > 0 ? (
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
          {data.applications_without_branch} application{data.applications_without_branch === 1 ? "" : "s"} have no branch
          and went straight to the committee. Assigning a customer to a branch sends any of their applications nobody has
          decided yet to that branch manager instead.
        </p>
      ) : null}
      {total === 0 ? (
        <EmptyState>Every credit officer, branch manager, and customer has a branch.</EmptyState>
      ) : activeBranches.length === 0 ? (
        <Banner kind="info">Create a branch first, then assign people to it here.</Banner>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {[...data.staff_missing_branch, ...data.customers_missing_branch].map((user) => (
            <AssignRow key={user.id} user={user} branches={activeBranches} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function AssignRow({ user, branches }: { user: UnassignedUser; branches: BranchResponse[] }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [branchId, setBranchId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function assign() {
    setError(null);
    setSaving(true);
    try {
      const result = await apiRequest<AssignBranchResponse>(`/admin/users/${user.id}/branch`, {
        method: "PATCH",
        body: { branch_id: Number(branchId) },
      });
      const moved = result.rerouted_application_ids.length;
      toast(
        `${user.full_name} assigned${moved ? ` — ${moved} application${moved === 1 ? "" : "s"} sent to branch review` : ""}.`,
        "success",
      );
      void queryClient.invalidateQueries({ queryKey: ["admin", "branch-assignment"] });
      void queryClient.invalidateQueries({ queryKey: ["staff"] });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-2.5">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-50">
          {user.full_name}
          {!user.is_active ? <span className="ml-2 text-xs text-slate-400">(inactive)</span> : null}
        </p>
        <p className="truncate text-xs text-slate-500 dark:text-slate-400">
          {ROLE_LABEL[user.role] ?? user.role} · {user.email}
        </p>
        {error ? <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p> : null}
      </div>
      <div className="flex items-center gap-2">
        <Select aria-label={`Branch for ${user.full_name}`} value={branchId} onChange={(e) => setBranchId(e.target.value)} className="w-44">
          <option value="">Choose branch…</option>
          {branches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name} ({b.code})
            </option>
          ))}
        </Select>
        <Button className="px-3 py-1.5 text-xs" disabled={!branchId || saving} onClick={() => void assign()}>
          {saving ? "Saving…" : "Assign"}
        </Button>
      </div>
    </li>
  );
}

/** A branch's own signup link: customers who use it are placed in that
 * branch automatically (the server checks the code). */
export function useSignupCode() {
  return useQuery({
    queryKey: ["admin", "signup-link"],
    queryFn: () => apiRequest<{ signup_code: string }>("/admin/signup-link"),
    staleTime: 5 * 60_000,
  });
}

export function branchSignupUrl(signupCode: string, branchCode?: string): string {
  const base = `${window.location.origin}/apply/${encodeURIComponent(signupCode)}`;
  return branchCode ? `${base}?branch=${encodeURIComponent(branchCode)}` : base;
}

export function CopyLinkButton({ url }: { url: string }) {
  const toast = useToast();
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      toast("Signup link copied.", "success");
    } catch {
      window.prompt("Copy this signup link:", url);
    }
  }
  return (
    <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => void copy()} title={url}>
      Copy signup link
    </Button>
  );
}
