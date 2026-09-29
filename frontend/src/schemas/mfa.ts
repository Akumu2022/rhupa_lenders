export interface MfaEnrollResponse {
  otpauth_uri: string;
  qr_code_data_uri: string;
}

export interface MfaConfirmResponse {
  recovery_codes: string[];
}
