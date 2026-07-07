export type VerificationMode = "claim" | "report";

export type VerifyResponse = {
  case_id?: string;
  created_case?: Record<string, unknown>;
  investigation_start?: Record<string, unknown>;
  error?: string;
  backend_status?: number;
  backend_detail?: Record<string, unknown>;
};
