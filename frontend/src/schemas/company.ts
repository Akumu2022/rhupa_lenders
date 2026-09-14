import { z } from "zod";

const HEX_COLOR_RE = /^#[0-9A-Fa-f]{6}$/;
const hexColor = z
  .string()
  .regex(HEX_COLOR_RE, "Must be a hex color like #4F46E5")
  .optional()
  .or(z.literal(""));

// Mirrors backend app/schemas/company.py::CompanyBrandingFields
const brandingFields = {
  tagline: z.string().optional(),
  logo_url: z.string().optional(),
  brand_primary_color: hexColor,
  brand_accent_color: hexColor,
  support_email: z.string().email("Enter a valid email").optional().or(z.literal("")),
  support_phone: z.string().optional(),
  address: z.string().optional(),
};

// Mirrors backend app/schemas/company.py
export const companyCreateSchema = z.object({
  name: z.string().min(1, "Company name is required"),
  admin_email: z.string().email("Enter a valid email"),
  admin_password: z.string().min(8, "At least 8 characters"),
  admin_full_name: z.string().min(1, "Admin name is required"),
  legal_name: z.string().optional(),
  registration_number: z.string().optional(),
  ...brandingFields,
});
export type CompanyCreateInput = z.infer<typeof companyCreateSchema>;

export const companyProfileUpdateSchema = z.object(brandingFields);
export type CompanyProfileUpdateInput = z.infer<typeof companyProfileUpdateSchema>;

/** Optional text fields round-trip as "" from an empty form input, but the
 * backend's Optional[str]/EmailStr fields want either a real value or the
 * field omitted entirely — never "" (e.g. EmailStr rejects it outright). */
export function omitBlankFields<T extends Record<string, unknown>>(values: T): Partial<T> {
  const cleaned: Partial<T> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value !== "" && value !== undefined) {
      (cleaned as Record<string, unknown>)[key] = value;
    }
  }
  return cleaned;
}

export interface CompanyResponse {
  id: number;
  name: string;
  status: "active" | "suspended";
  signup_code: string;
  legal_name: string | null;
  tagline: string | null;
  logo_url: string | null;
  brand_primary_color: string | null;
  brand_accent_color: string | null;
  support_email: string | null;
  support_phone: string | null;
  address: string | null;
  registration_number: string | null;
}

export interface CompanyInfoResponse {
  id: number;
  name: string;
  status: "active" | "suspended";
  tagline: string | null;
  logo_url: string | null;
  brand_primary_color: string | null;
  brand_accent_color: string | null;
  support_email: string | null;
  support_phone: string | null;
  address: string | null;
}

export interface SignupCodeInfoResponse {
  company_name: string;
  active: boolean;
  logo_url: string | null;
  brand_primary_color: string | null;
}

export const statusChangeSchema = z.object({
  reason: z.string().min(1, "A reason is required"),
});
export type StatusChangeInput = z.infer<typeof statusChangeSchema>;

export const customerSignupSchema = z.object({
  signup_code: z.string().min(1, "Signup code is required"),
  email: z.string().email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
  full_name: z.string().min(1, "Name is required"),
});
export type CustomerSignupInput = z.infer<typeof customerSignupSchema>;
