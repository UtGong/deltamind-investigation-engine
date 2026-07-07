"use client";

import { Activity, AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type RecordValue = Record<string, unknown>;

type VerificationState = {
  case_id: string;
  case_available: boolean;
  case_status: string;
  investigation_available: boolean;
  certificate_available: boolean;
  evidence_graph_available: boolean;
  error_available: boolean;
  case: RecordValue | null;
  investigation: RecordValue | null;
  trust_certificate: RecordValue | null;
  evidence_graph: RecordValue | null;
  error: RecordValue | null;
};

function isRecord(value: unknown): value is RecordValue {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getString(source: RecordValue | null | undefined, key: string): string | null {
  const value = source?.[key];
  return typeof value === "string" ? value : null;
}

function getNumber(source: RecordValue | null | undefined, key: string): number | null {
  const value = source?.[key];
  return typeof value === "number" ? value : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

async function loadState(caseId: string): Promise<VerificationState> {
  const response = await fetch(`/api/verification-state/${caseId}`, { cache: "no-store" });
  const payload = (await response.json()) as unknown;

  if (!response.ok) {
    const detail = isRecord(payload) ? getString(payload, "detail") : null;
    throw new Error(detail ?? `Verification state failed with ${response.status}.`);
  }

  if (!isRecord(payload)) {
    throw new Error("Backend returned an invalid verification state.");
  }

  return payload as VerificationState;
}

export function CaseResultPoller({ caseId }: { caseId: string }) {
  const [state, setState] = useState<VerificationState | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        const nextState = await loadState(caseId);
        if (!cancelled) {
          setState(nextState);
          setRequestError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setRequestError(error instanceof Error ? error.message : "Failed to load verification state.");
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [caseId, tick]);

  const status = state?.case_status ?? "unknown";
  const isCompleted = status === "completed";
  const isFailed = status === "failed";
  const isTerminal = isCompleted || isFailed;

  useEffect(() => {
    if (isTerminal) return;
    const timer = window.setTimeout(() => setTick((value) => value + 1), 4000);
    return () => window.clearTimeout(timer);
  }, [isTerminal, tick]);

  const investigation = state?.investigation ?? null;
  const certificate = state?.trust_certificate ?? null;
  const graph = state?.evidence_graph ?? null;
  const casePayload = state?.case ?? null;
  const backendError = state?.error ?? null;

  const evidenceItems = useMemo(() => asArray(investigation?.evidence), [investigation]);
  const stanceResults = useMemo(() => asArray(investigation?.stances), [investigation]);
  const corrections = useMemo(() => asArray(investigation?.corrections), [investigation]);
  const activeCorrections = corrections.filter((item) => isRecord(item) && item.needs_correction === true);

  const verdict =
    getString(investigation, "case_verdict") ??
    getString(certificate, "overall_verdict") ??
    (isFailed ? "failed" : isCompleted ? "unknown" : "running");
  const confidence = getNumber(investigation, "confidence") ?? getNumber(certificate, "confidence");
  const trustIndex = getNumber(certificate, "trust_index");

  return (
    <div className="space-y-6">
      <section className="border border-slate-800 bg-slate-900/70 p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Case Result</p>
            <h1 className="mt-3 break-all text-3xl font-semibold text-white">{caseId}</h1>
          </div>
          <StatusBadge status={status} />
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-4">
          <Metric label="Verdict" value={verdict} />
          <Metric label="Confidence" value={confidence === null ? "N/A" : confidence.toFixed(3)} />
          <Metric label="Trust Index" value={trustIndex === null ? "N/A" : trustIndex.toFixed(3)} />
          <Metric label="State" value={status} />
        </div>
      </section>

      {(requestError || backendError) && (
        <section className="border border-rose-400/30 bg-rose-500/10 p-5 text-sm text-rose-100">
          {requestError ?? getString(backendError, "error_message") ?? getString(backendError, "message") ?? "Investigation failed."}
        </section>
      )}

      {!isTerminal && (
        <section className="border border-slate-800 bg-slate-900/60 p-5">
          <div className="mb-4 h-2 overflow-hidden bg-slate-800">
            <div className="h-full w-1/2 animate-pulse bg-cyan-300" />
          </div>
          <div className="flex items-center gap-2 text-slate-200">
            <Clock className="h-5 w-5 text-cyan-300" aria-hidden="true" />
            <h2 className="text-lg font-semibold">Investigation is running</h2>
          </div>
          <p className="mt-2 text-sm leading-7 text-slate-400">The backend is collecting evidence, classifying stance, scoring the case, and preparing certificate data.</p>
        </section>
      )}

      <Panel title="Verdict Summary">
        <KeyValue label="Verdict" value={verdict} />
        <KeyValue label="Confidence" value={confidence === null ? "N/A" : confidence.toFixed(3)} />
        <KeyValue label="Trust Index" value={trustIndex === null ? "N/A" : trustIndex.toFixed(3)} />
      </Panel>

      <Panel title="Submitted Input">
        <p className="text-sm leading-7 text-slate-300">{getString(casePayload, "input_text") ?? "Case input is not available yet."}</p>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Claim Correction">
          {activeCorrections.length === 0 ? (
            <EmptyText>No evidence-backed correction returned.</EmptyText>
          ) : (
            activeCorrections.map((item, index) => <Correction key={index} value={item} />)
          )}
        </Panel>

        <Panel title="Trust Certificate">
          <KeyValue label="Certificate" value={getString(certificate, "certificate_id") ?? "Not ready"} />
          <KeyValue label="Lifecycle" value={getString(certificate, "lifecycle_status") ?? "N/A"} />
          <KeyValue label="Evidence Count" value={String(asArray(certificate?.evidence_items).length || asArray(certificate?.sources).length)} />
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Evidence">
          {evidenceItems.length === 0 ? <EmptyText>No evidence items returned.</EmptyText> : evidenceItems.slice(0, 8).map((item, index) => <Evidence key={index} value={item} />)}
        </Panel>

        <Panel title="Stance Results">
          {stanceResults.length === 0 ? <EmptyText>No stance results returned.</EmptyText> : stanceResults.slice(0, 8).map((item, index) => <Stance key={index} value={item} />)}
        </Panel>
      </div>

      <Panel title="Evidence Graph Summary">
        <KeyValue label="Nodes" value={String(asArray(graph?.nodes).length)} />
        <KeyValue label="Edges" value={String(asArray(graph?.edges).length)} />
      </Panel>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const Icon = status === "completed" ? CheckCircle2 : status === "failed" ? AlertTriangle : Activity;
  const color = status === "completed" ? "text-emerald-200 border-emerald-400/30 bg-emerald-500/10" : status === "failed" ? "text-rose-100 border-rose-400/30 bg-rose-500/10" : "text-cyan-100 border-cyan-400/30 bg-cyan-500/10";
  return (
    <div className={`inline-flex items-center gap-2 border px-3 py-2 text-sm ${color}`}>
      <Icon className="h-4 w-4" aria-hidden="true" />
      {status}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-slate-800 bg-slate-950/70 p-4">
      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-white">{value}</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border border-slate-800 bg-slate-900/50">
      <div className="border-b border-slate-800 px-5 py-4">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
      </div>
      <div className="space-y-3 p-5">{children}</div>
    </section>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 bg-slate-950/60 px-4 py-3">
      <span className="text-sm text-slate-400">{label}</span>
      <span className="text-right text-sm font-medium text-slate-100">{value}</span>
    </div>
  );
}

function EmptyText({ children }: { children: string }) {
  return <p className="text-sm leading-7 text-slate-400">{children}</p>;
}

function Correction({ value }: { value: unknown }) {
  if (!isRecord(value)) return null;
  return (
    <div className="border border-emerald-400/30 bg-emerald-500/10 p-4">
      <p className="text-sm font-semibold text-emerald-100">{getString(value, "corrected_claim") ?? "Correction"}</p>
      <p className="mt-2 text-sm leading-6 text-emerald-50/80">{getString(value, "rationale") ?? "No rationale returned."}</p>
    </div>
  );
}

function Evidence({ value }: { value: unknown }) {
  if (!isRecord(value)) return null;
  return (
    <div className="border border-slate-800 bg-slate-950/60 p-4">
      <p className="text-sm font-semibold text-white">{getString(value, "title") ?? getString(value, "source_name") ?? "Evidence"}</p>
      <p className="mt-2 line-clamp-4 text-sm leading-6 text-slate-400">{getString(value, "evidence_text") ?? getString(value, "snippet") ?? "No text returned."}</p>
    </div>
  );
}

function Stance({ value }: { value: unknown }) {
  if (!isRecord(value)) return null;
  return (
    <div className="border border-slate-800 bg-slate-950/60 p-4">
      <KeyValue label="Stance" value={getString(value, "stance") ?? "unknown"} />
      <p className="mt-3 text-sm leading-6 text-slate-400">{getString(value, "rationale") ?? "No rationale returned."}</p>
    </div>
  );
}
