const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export type DashboardSummary = {
  certificate_count: number;
  active_count: number;
  review_required_count: number;
  average_trust_index: number;
};

export type CaseSummary = {
  case_id: string;
  title: string | null;
  input_type: string;
  input_text: string;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export function getDashboardSummary() {
  return fetchJson<DashboardSummary>("/api/v1/trust-certificates/recent/dashboard-summary?limit=20");
}

export function getCases() {
  return fetchJson<CaseSummary[]>("/api/v1/cases");
}
