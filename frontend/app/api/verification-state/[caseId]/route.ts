import { NextResponse } from "next/server";

const API_BASE_URL =
  process.env.BACKEND_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

type RouteContext = { params: Promise<{ caseId: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const { caseId } = await context.params;

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/cases/${caseId}/verification-state`, { cache: "no-store" });
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        case_id: caseId,
        case_available: false,
        case_status: "unknown",
        investigation_available: false,
        certificate_available: false,
        evidence_graph_available: false,
        error_available: true,
        case: null,
        investigation: null,
        trust_certificate: null,
        evidence_graph: null,
        error: {
          message: error instanceof Error ? error.message : "Failed to fetch backend verification state.",
          case_id: caseId,
          stage: "frontend_backend_proxy",
        },
      },
      { status: 502 },
    );
  }
}
