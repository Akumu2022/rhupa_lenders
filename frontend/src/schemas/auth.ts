import { z } from "zod";

// Mirrors backend app/schemas/auth.py
export const loginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});
export type LoginInput = z.infer<typeof loginSchema>;

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: string;
  company_id: number | null;
}

// CLAUDE.md §4/MFA: returned by POST /auth/login instead of TokenResponse
// when the account has MFA enabled.
export interface MfaRequiredResponse {
  mfa_required: true;
  mfa_token: string;
}

export function isMfaRequired(response: TokenResponse | MfaRequiredResponse): response is MfaRequiredResponse {
  return "mfa_required" in response && response.mfa_required === true;
}
