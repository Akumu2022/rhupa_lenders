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
