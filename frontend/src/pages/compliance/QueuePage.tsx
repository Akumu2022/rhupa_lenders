import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiRequest, fetchAuthedBlob, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, LoadingRow, PageHeader, SectionLabel, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import { kycStatusTone } from "../../schemas/compliance";
import type { ComplianceProfileResponse } from "../../schemas/compliance";

type StatusFilter = "pending" | "verified" | "rejected" | "all";

const STATUS_TABS: { value: StatusFilter; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "verified", label: "Verified" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

interface DocumentPreview {
  url: string;
  isImage: boolean;
}

/** Loads a KYC document as an inline preview (image) or a fallback link
 * (PDF) — the review drawer should show what was submitted, not make the
 * officer click through to another tab to see it. */
function useDocumentPreview(profileId: number, kind: "id_document" | "id_document_back" | "selfie") {
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    setPreview(null);
    setError(null);
    setIsLoading(true);

    fetchAuthedBlob(`/compliance/profiles/${profileId}/document/${kind}`)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setPreview({ url: objectUrl, isImage: blob.type.startsWith("image/") });
      })
      .catch((err) => setError(getErrorMessage(err, "Could not load document")))
      .finally(() => setIsLoading(false));

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [profileId, kind]);

  return { preview, error, isLoading };
}

function DocumentCard({ label, profileId, kind }: { label: string; profileId: number; kind: "id_document" | "id_document_back" | "selfie" }) {
  const { preview, error, isLoading } = useDocumentPreview(profileId, kind);

  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-slate-600 dark:text-slate-400">{label}</p>
      <div className="flex min-h-[8rem] items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
        {isLoading ? <LoadingRow label="Loading…" /> : null}
        {error ? <p className="p-3 text-center text-xs text-rose-600 dark:text-rose-400">{error}</p> : null}
        {preview?.isImage ? (
          <a href={preview.url} target="_blank" rel="noopener noreferrer" title="Open full size">
            <img src={preview.url} alt={label} className="max-h-64 w-full object-contain" />
          </a>
        ) : null}
        {preview && !preview.isImage ? (
          <a
            href={preview.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-1 p-4 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            Document uploaded (PDF) — open to view
          </a>
        ) : null}
      </div>
    </div>
  );
}

function ReviewDrawer({ profile, onClose }: { profile: ComplianceProfileResponse | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const isPending = profile?.kyc_status === "pending";

  useEffect(() => {
    setNotes("");
    setReason("");
    setActionError(null);
  }, [profile]);

  function invalidateAndClose(message: string) {
    // A verified/rejected Profile is also read under ["admin","kyc"] (company
    // KYC oversight) and ["customers", id] (credit officer's customer detail)
    // — invalidate all three read-paths for the same underlying row, not
    // just this page's own query.
    void queryClient.invalidateQueries({ queryKey: ["compliance", "history"] });
    void queryClient.invalidateQueries({ queryKey: ["admin", "kyc"] });
    void queryClient.invalidateQueries({ queryKey: ["customers"] });
    toast(message, "success");
    onClose();
  }

  const verify = useMutation({
    mutationFn: () =>
      apiRequest(`/compliance/profiles/${profile!.id}/verify`, { method: "POST", body: { notes: notes.trim() || null } }),
    onSuccess: () =>
      invalidateAndClose(`${profile!.customer_full_name} is verified and can now apply for a loan.`),
    onError: (err) => setActionError(getErrorMessage(err)),
  });

  const reject = useMutation({
    mutationFn: () => apiRequest(`/compliance/profiles/${profile!.id}/reject`, { method: "POST", body: { reason } }),
    onSuccess: () =>
      invalidateAndClose(`${profile!.customer_full_name}'s submission was rejected and sent back to them.`),
    onError: (err) => setActionError(getErrorMessage(err)),
  });

  return (
    <Drawer open={profile !== null} onClose={onClose} title={profile ? profile.customer_full_name : ""}>
      {profile ? (
        <div className="space-y-5">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">{profile.customer_email}</p>
            <Badge tone={kycStatusTone(profile.kyc_status)}>{profile.kyc_status}</Badge>
          </div>

          {!isPending ? (
            <Banner kind={profile.kyc_status === "verified" ? "success" : "info"}>
              Decided {profile.reviewed_at ? new Date(profile.reviewed_at).toLocaleString() : ""}
              {profile.review_notes ? ` — "${profile.review_notes}"` : ""}
            </Banner>
          ) : null}

          <div>
            <SectionLabel>Submitted details</SectionLabel>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              {profile.customer_number ? (
                <div className="col-span-2">
                  <dt className="text-slate-500 dark:text-slate-400">Customer #</dt>
                  <dd className="font-mono font-medium text-slate-900 dark:text-slate-100">{profile.customer_number}</dd>
                </div>
              ) : null}
              {profile.first_name || profile.last_name ? (
                <div className="col-span-2">
                  <dt className="text-slate-500 dark:text-slate-400">Full name</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">
                    {[profile.first_name, profile.middle_name, profile.last_name].filter(Boolean).join(" ")}
                  </dd>
                </div>
              ) : null}
              <div>
                <dt className="text-slate-500 dark:text-slate-400">{profile.id_type === "passport" ? "Passport" : "National ID"}</dt>
                <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.national_id_number}</dd>
              </div>
              <div>
                <dt className="text-slate-500 dark:text-slate-400">Phone</dt>
                <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.phone_number}</dd>
              </div>
              {profile.gender ? (
                <div>
                  <dt className="text-slate-500 dark:text-slate-400">Gender</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.gender}</dd>
                </div>
              ) : null}
              {profile.nationality ? (
                <div>
                  <dt className="text-slate-500 dark:text-slate-400">Nationality</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.nationality}</dd>
                </div>
              ) : null}
              {profile.marital_status ? (
                <div>
                  <dt className="text-slate-500 dark:text-slate-400">Marital status</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.marital_status}</dd>
                </div>
              ) : null}
              {profile.dependants_count != null ? (
                <div>
                  <dt className="text-slate-500 dark:text-slate-400">Dependants</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.dependants_count}</dd>
                </div>
              ) : null}
              <div className="col-span-2">
                <dt className="text-slate-500 dark:text-slate-400">Address</dt>
                <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.residential_address}</dd>
              </div>
              <div>
                <dt className="text-slate-500 dark:text-slate-400">Employment</dt>
                <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.employment_status}</dd>
              </div>
              <div>
                <dt className="text-slate-500 dark:text-slate-400">Occupation</dt>
                <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.occupation}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-slate-500 dark:text-slate-400">Monthly income</dt>
                <dd className="font-medium text-slate-900 dark:text-slate-100">KES {profile.monthly_income}</dd>
              </div>
            </dl>
          </div>

          {profile.next_of_kin_name ? (
            <div>
              <SectionLabel>Next of kin</SectionLabel>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <div>
                  <dt className="text-slate-500 dark:text-slate-400">Name</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.next_of_kin_name}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 dark:text-slate-400">Relationship</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.next_of_kin_relationship}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-slate-500 dark:text-slate-400">Phone</dt>
                  <dd className="font-medium text-slate-900 dark:text-slate-100">{profile.next_of_kin_phone}</dd>
                </div>
              </dl>
            </div>
          ) : null}

          <div>
            <SectionLabel>Documents submitted for review</SectionLabel>
            <div className="grid grid-cols-2 gap-3">
              <DocumentCard label="ID front" profileId={profile.id} kind="id_document" />
              {profile.has_id_document_back ? (
                <DocumentCard label="ID back" profileId={profile.id} kind="id_document_back" />
              ) : (
                <div>
                  <p className="mb-1.5 text-xs font-medium text-slate-600 dark:text-slate-400">ID back</p>
                  <div className="flex min-h-[8rem] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 p-3 text-center text-xs text-slate-400 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-500">
                    Not provided (submitted before this was required)
                  </div>
                </div>
              )}
              {profile.has_selfie ? (
                <DocumentCard label="Selfie / passport photo" profileId={profile.id} kind="selfie" />
              ) : (
                <div>
                  <p className="mb-1.5 text-xs font-medium text-slate-600 dark:text-slate-400">Selfie / passport photo</p>
                  <div className="flex min-h-[8rem] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 p-3 text-center text-xs text-slate-400 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-500">
                    Not provided
                  </div>
                </div>
              )}
            </div>
          </div>

          {isPending ? (
            <div className="space-y-4 border-t border-slate-100 pt-4 dark:border-slate-800">
              <SectionLabel>Decision</SectionLabel>
              <div>
                <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
                  Confirm details are accepted (notes optional)
                </label>
                <p className="mb-1.5 text-xs text-slate-400 dark:text-slate-500">
                  Approving unlocks this customer to apply for a loan — it does not submit an application for them.
                  Once they apply, it automatically reaches the credit officer's queue; no manual hand-off needed.
                </p>
                <div className="flex gap-2">
                  <TextInput placeholder="e.g. ID matches selfie" value={notes} onChange={(e) => setNotes(e.target.value)} />
                  <Button disabled={verify.isPending} onClick={() => verify.mutate()}>
                    {verify.isPending ? "Confirming…" : "Confirm & verify"}
                  </Button>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
                  Reject (reason required)
                </label>
                <div className="mt-1 flex gap-2">
                  <TextInput placeholder="e.g. ID photo is blurry" value={reason} onChange={(e) => setReason(e.target.value)} />
                  <Button variant="danger" disabled={!reason.trim() || reject.isPending} onClick={() => reject.mutate()}>
                    Reject
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="border-t border-slate-100 pt-4 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
              This decision is final unless a system_administrator overrides it — kept here for reference.
            </div>
          )}
          {actionError ? <Banner kind="error">{actionError}</Banner> : null}
        </div>
      ) : null}
    </Drawer>
  );
}

export function ComplianceQueuePage() {
  const [searchParams] = useSearchParams();
  const initialStatus = (searchParams.get("status") as StatusFilter | null) ?? "pending";
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(
    STATUS_TABS.some((t) => t.value === initialStatus) ? initialStatus : "pending",
  );
  const [selected, setSelected] = useState<ComplianceProfileResponse | null>(null);

  const historyQuery = useQuery({
    queryKey: ["compliance", "history"],
    queryFn: () => apiRequest<ComplianceProfileResponse[]>("/compliance/history"),
  });

  const filtered = useMemo(() => {
    if (!historyQuery.data) return undefined;
    if (statusFilter === "all") return historyQuery.data;
    return historyQuery.data.filter((p) => p.kyc_status === statusFilter);
  }, [historyQuery.data, statusFilter]);

  return (
    <AppShell>
      <PageHeader title="KYC review queue" subtitle="Verify identity before a customer can apply for a loan" />

      <div className="mb-4 flex gap-1 rounded-lg bg-slate-100 p-1 text-sm dark:bg-slate-800">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setStatusFilter(tab.value)}
            className={`flex-1 rounded-md px-3 py-1.5 font-medium transition-colors ${
              statusFilter === tab.value
                ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100"
                : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Card>
        <DataTable
          columns={[
            { key: "name", header: "Customer", sortable: true, accessor: (p: ComplianceProfileResponse) => p.customer_full_name },
            { key: "email", header: "Email", accessor: (p) => p.customer_email },
            { key: "national_id", header: "National ID", accessor: (p) => p.national_id_number },
            {
              key: "status",
              header: "Status",
              accessor: (p) => p.kyc_status,
              render: (p) => <Badge tone={kycStatusTone(p.kyc_status)}>{p.kyc_status}</Badge>,
            },
            {
              key: "created_at",
              header: "Submitted",
              sortable: true,
              accessor: (p) => p.created_at,
              render: (p) => new Date(p.created_at).toLocaleString(),
            },
          ]}
          data={filtered}
          getRowId={(p) => p.id}
          isLoading={historyQuery.isLoading}
          isError={historyQuery.isError}
          searchKeys={["name", "email", "national_id"]}
          searchPlaceholder="Search by name, email, or ID…"
          emptyMessage="Nothing here."
          onRowClick={(p) => setSelected(p)}
          rowActions={(p) => (
            <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">
              {p.kyc_status === "pending" ? "Review →" : "View →"}
            </span>
          )}
        />
      </Card>

      <ReviewDrawer profile={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
