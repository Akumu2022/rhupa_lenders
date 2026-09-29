import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../api/client";
import { AppShell } from "../components/AppShell";
import { Banner, Button, Card, Field, PageHeader, PasswordInput, SectionLabel, TextInput } from "../components/ui";
import { useToast } from "../components/toast";
import type { MfaConfirmResponse, MfaEnrollResponse } from "../schemas/mfa";

/** CLAUDE.md §4/MFA: self-service enrollment for any staff role (never
 * shown/usable for customers — the backend 403s an enroll attempt, and the
 * nav item is only wired into staff NAV_BY_ROLE entries). Three states:
 * not enrolled -> scanning a QR code -> enrolled (with a disable form). */
export function SecurityPage() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const statusQuery = useQuery({
    queryKey: ["auth", "mfa", "status"],
    queryFn: () => apiRequest<{ mfa_enabled: boolean }>("/auth/mfa/status"),
  });

  const [enrollment, setEnrollment] = useState<MfaEnrollResponse | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [savedRecoveryCodes, setSavedRecoveryCodes] = useState<string[] | null>(null);

  const startEnroll = useMutation({
    mutationFn: () => apiRequest<MfaEnrollResponse>("/auth/mfa/enroll", { method: "POST" }),
    onSuccess: (result) => setEnrollment(result),
    onError: (err) => toast(getErrorMessage(err), "error"),
  });

  const confirm = useMutation({
    mutationFn: () => apiRequest<MfaConfirmResponse>("/auth/mfa/confirm", { method: "POST", body: { code: confirmCode } }),
    onSuccess: (result) => {
      setSavedRecoveryCodes(result.recovery_codes);
      setEnrollment(null);
      setConfirmCode("");
      setConfirmError(null);
      void queryClient.invalidateQueries({ queryKey: ["auth", "mfa", "status"] });
    },
    onError: (err) => setConfirmError(getErrorMessage(err)),
  });

  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [disableError, setDisableError] = useState<string | null>(null);

  const disable = useMutation({
    mutationFn: () =>
      apiRequest("/auth/mfa/disable", { method: "POST", body: { password: disablePassword, code: disableCode } }),
    onSuccess: () => {
      toast("Two-factor authentication disabled.", "success");
      setDisablePassword("");
      setDisableCode("");
      setDisableError(null);
      void queryClient.invalidateQueries({ queryKey: ["auth", "mfa", "status"] });
    },
    onError: (err) => setDisableError(getErrorMessage(err)),
  });

  const mfaEnabled = statusQuery.data?.mfa_enabled ?? false;

  return (
    <AppShell>
      <PageHeader title="Security" subtitle="Two-factor authentication for your account" />

      {savedRecoveryCodes ? (
        <Card className="mb-4">
          <SectionLabel>Save your recovery codes</SectionLabel>
          <Banner kind="info">
            Each code can be used once if you lose access to your authenticator app. Store them somewhere safe —
            they won't be shown again.
          </Banner>
          <div className="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 font-mono text-sm dark:bg-slate-800/60">
            {savedRecoveryCodes.map((code) => (
              <span key={code}>{code}</span>
            ))}
          </div>
          <Button className="mt-4" onClick={() => setSavedRecoveryCodes(null)}>
            I've saved these
          </Button>
        </Card>
      ) : null}

      {statusQuery.isLoading ? (
        <Card>Loading…</Card>
      ) : mfaEnabled ? (
        <Card>
          <SectionLabel>Two-factor authentication is enabled</SectionLabel>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            You'll be asked for a code from your authenticator app every time you sign in.
          </p>
          <div className="mt-4 space-y-3 border-t border-slate-100 pt-4 dark:border-slate-800">
            <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
              To disable, confirm your password and a current code
            </p>
            <Field label="Password">
              <PasswordInput value={disablePassword} onChange={(e) => setDisablePassword(e.target.value)} />
            </Field>
            <Field label="6-digit code">
              <TextInput
                inputMode="numeric"
                maxLength={6}
                value={disableCode}
                onChange={(e) => setDisableCode(e.target.value)}
              />
            </Field>
            {disableError ? <Banner kind="error">{disableError}</Banner> : null}
            <Button
              variant="danger"
              disabled={!disablePassword.trim() || !disableCode.trim() || disable.isPending}
              onClick={() => disable.mutate()}
            >
              {disable.isPending ? "Disabling…" : "Disable two-factor authentication"}
            </Button>
          </div>
        </Card>
      ) : enrollment ? (
        <Card>
          <SectionLabel>Scan this code with your authenticator app</SectionLabel>
          <div className="flex flex-col items-center gap-3 py-2">
            <img src={enrollment.qr_code_data_uri} alt="MFA enrollment QR code" className="h-48 w-48 rounded-lg border border-slate-200 dark:border-slate-700" />
            <p className="text-center text-xs text-slate-500 dark:text-slate-400">
              Can't scan it? Enter this manually:{" "}
              <span className="font-mono">{new URL(enrollment.otpauth_uri).searchParams.get("secret")}</span>
            </p>
          </div>
          <div className="mt-3 space-y-3 border-t border-slate-100 pt-4 dark:border-slate-800">
            <Field label="Enter the 6-digit code to confirm">
              <TextInput inputMode="numeric" maxLength={6} value={confirmCode} onChange={(e) => setConfirmCode(e.target.value)} />
            </Field>
            {confirmError ? <Banner kind="error">{confirmError}</Banner> : null}
            <div className="flex gap-2">
              <Button disabled={!confirmCode.trim() || confirm.isPending} onClick={() => confirm.mutate()}>
                {confirm.isPending ? "Confirming…" : "Confirm"}
              </Button>
              <Button variant="secondary" onClick={() => setEnrollment(null)}>
                Cancel
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <Card>
          <SectionLabel>Two-factor authentication is not enabled</SectionLabel>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Add an extra layer of protection using an authenticator app (e.g. Google Authenticator, Authy).
          </p>
          <Button className="mt-4" disabled={startEnroll.isPending} onClick={() => startEnroll.mutate()}>
            {startEnroll.isPending ? "Starting…" : "Enable two-factor authentication"}
          </Button>
        </Card>
      )}
    </AppShell>
  );
}
