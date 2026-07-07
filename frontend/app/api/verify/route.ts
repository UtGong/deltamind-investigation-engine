import { NextResponse } from "next/server";

const API_BASE_URL =
  process.env.BACKEND_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function readJson(response: Response): Promise<Record<string, unknown>> {
  try {
    const payload = (await response.json()) as unknown;
    return isRecord(payload) ? payload : {};
  } catch {
    return {};
  }
}

function extractCaseId(payload: Record<string, unknown>): string | null {
  const value = payload.case_id ?? payload.id;
  return typeof value === "string" ? value : null;
}

export async function POST(request: Request) {
  const body = (await request.json()) as { text?: string; mode?: "claim" | "report" };
  const text = body.text?.trim();
  const mode = body.mode ?? "claim";

  if (!text) {
    return NextResponse.json({ error: "Please enter a claim or report to verify." }, { status: 400 });
  }

  const createResponse = await fetch(`${API_BASE_URL}/api/v1/cases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      input_type: mode === "report" ? "article_text" : "claim",
      input_text: text,
      title: mode === "report" ? "Frontend report verification" : "Frontend claim verification",
    }),
  });

  const createdCase = await readJson(createResponse);

  if (!createResponse.ok) {
    return NextResponse.json(
      { error: "Backend failed to create verification case.", backend_status: createResponse.status, backend_detail: createdCase },
      { status: createResponse.status },
    );
  }

  const caseId = extractCaseId(createdCase);
  if (!caseId) {
    return NextResponse.json(
      { error: "Backend created a case but did not return a case id.", backend_detail: createdCase },
      { status: 500 },
    );
  }

  const startResponse = await fetch(`${API_BASE_URL}/api/v1/cases/${caseId}/investigate-async`, { method: "POST" });
  const started = await readJson(startResponse);

  if (!startResponse.ok) {
    return NextResponse.json(
      { error: "Backend failed to start investigation.", case_id: caseId, backend_status: startResponse.status, backend_detail: started },
      { status: startResponse.status },
    );
  }

  return NextResponse.json({ case_id: caseId, created_case: createdCase, investigation_start: started });
}
