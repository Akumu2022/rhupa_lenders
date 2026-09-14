import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiRequest, ApiError, formatApiErrorDetail } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { Banner, Button, Card, Field, LoadingRow, PageHeader, TextInput } from "../../components/ui";
import { ThemeToggle } from "../../components/ThemeToggle";
import { customerSignupSchema, type CustomerSignupInput, type SignupCodeInfoResponse } from "../../schemas/company";
import type { TokenResponse } from "../../schemas/auth";

export function CustomerSignupPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const { code } = useParams<{ code?: string }>();
  const [serverError, setServerError] = useState<string | null>(null);

  // CLAUDE.md §17: on the happy path (a /apply/:code link) the code is never
  // typed or shown — it's resolved and confirmed before the form even
  // renders. The manual code field only exists as a fallback on the bare
  // /signup page for someone who landed here without a link.
  const codeInfoQuery = useQuery({
    queryKey: ["signup", "resolve", code],
    queryFn: () => apiRequest<SignupCodeInfoResponse>(`/signup/resolve/${code}`, { auth: false }),
    enabled: Boolean(code),
    retry: false,
  });

  // CLAUDE.md §21: tenant supplies DATA (a logo, a color) — the platform's
  // fixed layout/shell renders it. Falls back to the platform default badge
  // and gradient below when a company hasn't set branding.
  const brandColor = codeInfoQuery.data?.brand_primary_color ?? undefined;
  const brandLogo = codeInfoQuery.data?.logo_url ?? undefined;

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CustomerSignupInput>({
    resolver: zodResolver(customerSignupSchema),
    defaultValues: { signup_code: code ?? "" },
  });

  async function onSubmit(values: CustomerSignupInput) {
    setServerError(null);
    try {
      // The server resolves signup_code -> company_id and hardcodes role;
      // nothing here lets the client choose either (CLAUDE.md §7).
      const response = await apiRequest<TokenResponse>("/signup", {
        method: "POST",
        body: values,
        auth: false,
      });
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

  // A link with a code that turned out to be invalid, expired, or inactive —
  // never let the customer fill out a form that can't possibly succeed.
  const linkIsBroken = Boolean(code) && (codeInfoQuery.isError || codeInfoQuery.data?.active === false);
  const canShowForm = !code || (codeInfoQuery.data?.active === true);

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-[#f6f5fb] to-violet-50 px-4 dark:from-indigo-950/40 dark:via-[#0b0e14] dark:to-violet-950/30">
      <ThemeToggle className="absolute right-4 top-4" />
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          {brandLogo ? (
            <img src={brandLogo} alt="" className="h-11 w-11 rounded-xl object-cover shadow-lg" />
          ) : (
            <span
              className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 text-lg font-bold text-white shadow-lg shadow-indigo-600/30"
              style={brandColor ? { background: brandColor } : undefined}
            >
              {codeInfoQuery.data?.company_name?.[0]?.toUpperCase() ?? "R"}
            </span>
          )}
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">
            {codeInfoQuery.data?.company_name ?? "Rupha Royals · Lending Platform"}
          </p>
        </div>
        <Card>
          {code && codeInfoQuery.isLoading ? (
            <>
              <PageHeader title="Create your account" />
              <LoadingRow label="Checking your signup link…" />
            </>
          ) : null}

          {linkIsBroken ? (
            <>
              <PageHeader title="Create your account" />
              <Banner kind="error">This signup link is invalid or no longer active.</Banner>
              <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
                Have a company code instead?{" "}
                <Link to="/signup" className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300">
                  Enter it manually
                </Link>
                .
              </p>
            </>
          ) : null}

          {canShowForm ? (
            <>
              <PageHeader
                title="Create your account"
                subtitle={
                  code && codeInfoQuery.data
                    ? `Create your account with ${codeInfoQuery.data.company_name}`
                    : "Enter the signup code your lender gave you"
                }
              />
              <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
                {code ? (
                  <input type="hidden" {...register("signup_code")} />
                ) : (
                  <Field label="Company signup code" error={errors.signup_code?.message}>
                    <TextInput {...register("signup_code")} />
                  </Field>
                )}
                <Field label="Full name" error={errors.full_name?.message}>
                  <TextInput {...register("full_name")} />
                </Field>
                <Field label="Email" error={errors.email?.message}>
                  <TextInput type="email" autoComplete="email" {...register("email")} />
                </Field>
                <Field label="Password" error={errors.password?.message}>
                  <TextInput type="password" autoComplete="new-password" {...register("password")} />
                </Field>
                {serverError ? <Banner kind="error">{serverError}</Banner> : null}
                <Button
                  type="submit"
                  className="w-full"
                  disabled={isSubmitting}
                  style={brandColor ? { backgroundColor: brandColor } : undefined}
                >
                  {isSubmitting ? "Creating account…" : "Create account"}
                </Button>
              </form>
            </>
          ) : null}
        </Card>
      </div>
    </div>
  );
}
