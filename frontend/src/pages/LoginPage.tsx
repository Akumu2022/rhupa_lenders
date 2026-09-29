import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type FormEvent } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { apiRequest, ApiError, formatApiErrorDetail } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Banner, Button, Card, Field, PageHeader, PasswordInput, TextInput } from "../components/ui";
import { ThemeToggle } from "../components/ThemeToggle";
import { isMfaRequired, loginSchema, type LoginInput, type MfaRequiredResponse, type TokenResponse } from "../schemas/auth";

/** CLAUDE.md §4/MFA: step 2 of login, shown only when the account has MFA
 * enabled — a 6-digit authenticator code, or a one-time recovery code as a
 * fallback. Customers never reach this (login never returns mfa_required
 * for them). */
function MfaStep({ mfaToken, onBack }: { mfaToken: string; onBack: () => void }) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [useRecoveryCode, setUseRecoveryCode] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const response = await apiRequest<TokenResponse>("/auth/mfa/verify", {
        method: "POST",
        body: useRecoveryCode ? { mfa_token: mfaToken, recovery_code: value } : { mfa_token: mfaToken, code: value },
        auth: false,
      });
      login({ accessToken: response.access_token, role: response.role, companyId: response.company_id });
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? formatApiErrorDetail(err.detail) : "Could not reach the server");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <PageHeader
        title="Verification required"
        subtitle={useRecoveryCode ? "Enter one of your saved recovery codes" : "Enter the 6-digit code from your authenticator app"}
      />
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        <Field label={useRecoveryCode ? "Recovery code" : "6-digit code"}>
          <TextInput
            autoFocus
            inputMode={useRecoveryCode ? "text" : "numeric"}
            maxLength={useRecoveryCode ? undefined : 6}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </Field>
        {error ? <Banner kind="error">{error}</Banner> : null}
        <Button type="submit" className="w-full" disabled={!value.trim() || submitting}>
          {submitting ? "Verifying…" : "Verify"}
        </Button>
      </form>
      <div className="mt-4 flex items-center justify-between text-xs">
        <button
          type="button"
          className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
          onClick={() => {
            setUseRecoveryCode((v) => !v);
            setValue("");
            setError(null);
          }}
        >
          {useRecoveryCode ? "Use an authenticator code instead" : "Use a recovery code instead"}
        </button>
        <button type="button" className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300" onClick={onBack}>
          Back to sign in
        </button>
      </div>
    </Card>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState<MfaRequiredResponse | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) });

  async function onSubmit(values: LoginInput) {
    setServerError(null);
    try {
      const response = await apiRequest<TokenResponse | MfaRequiredResponse>("/auth/login", {
        method: "POST",
        body: values,
        auth: false,
      });
      if (isMfaRequired(response)) {
        setPending(response);
        return;
      }
      login({ accessToken: response.access_token, role: response.role, companyId: response.company_id });
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(formatApiErrorDetail(err.detail));
      } else {
        setServerError("Could not reach the server");
      }
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-[#f6f5fb] to-violet-50 px-4 dark:from-indigo-950/40 dark:via-[#0b0e14] dark:to-violet-950/30">
      <ThemeToggle className="absolute right-4 top-4" />
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 text-lg font-bold text-white shadow-lg shadow-indigo-600/30">
            R
          </span>
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">Rupha Royals · Lending Platform</p>
        </div>
        {pending ? (
          <MfaStep mfaToken={pending.mfa_token} onBack={() => setPending(null)} />
        ) : (
          <Card>
            <PageHeader title="Sign in" subtitle="Welcome back — enter your details to continue" />
            <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
              <Field label="Email" error={errors.email?.message}>
                <TextInput type="email" autoComplete="email" {...register("email")} />
              </Field>
              <Field label="Password" error={errors.password?.message}>
                <PasswordInput autoComplete="current-password" {...register("password")} />
              </Field>
              {serverError ? <Banner kind="error">{serverError}</Banner> : null}
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? "Signing in…" : "Sign in"}
              </Button>
            </form>
            <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
              Signing up as a customer?{" "}
              <Link to="/signup" className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300">
                Use your company's signup code
              </Link>
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
