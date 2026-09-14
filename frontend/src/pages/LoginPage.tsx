import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { apiRequest, ApiError, formatApiErrorDetail } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Banner, Button, Card, Field, PageHeader, TextInput } from "../components/ui";
import { ThemeToggle } from "../components/ThemeToggle";
import { loginSchema, type LoginInput, type TokenResponse } from "../schemas/auth";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) });

  async function onSubmit(values: LoginInput) {
    setServerError(null);
    try {
      const response = await apiRequest<TokenResponse>("/auth/login", {
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
        <Card>
          <PageHeader title="Sign in" subtitle="Welcome back — enter your details to continue" />
          <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <Field label="Email" error={errors.email?.message}>
              <TextInput type="email" autoComplete="email" {...register("email")} />
            </Field>
            <Field label="Password" error={errors.password?.message}>
              <TextInput type="password" autoComplete="current-password" {...register("password")} />
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
      </div>
    </div>
  );
}
