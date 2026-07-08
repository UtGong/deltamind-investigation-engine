"use client";

import Link from "next/link";
import { Activity, AlertTriangle, CheckCircle2, Clock, Fingerprint, Gauge, Plus, Route, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EvidenceGraphVisualizer } from "@/components/EvidenceGraphVisualizer";

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

function getDate(source: RecordValue | null | undefined, key: string): Date | null {
  const value = source?.[key];
  if (typeof value !== "string") return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asStringArray(value: unknown): string[] {
  return asArray(value).filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function formatRuntime(start: Date | null, end: Date | null, fallback: string) {
  if (!start) return fallback;
  const elapsedMs = Math.max(0, (end ?? new Date()).getTime() - start.getTime());
  const seconds = Math.floor(elapsedMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
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
  const agentRuns = useMemo(() => asArray(investigation?.agent_runs), [investigation]);
  const plannerRuns = useMemo(
    () =>
      agentRuns.filter(
        (item) =>
          isRecord(item) &&
          (getString(item, "agent_name")?.includes("search_planning") ||
            (isRecord(item.metadata) && item.metadata.stage === "search_planning")),
      ),
    [agentRuns],
  );
  const activeCorrections = corrections.filter((item) => isRecord(item) && item.needs_correction === true);
  const submittedClaim = getString(casePayload, "input_text") ?? "Waiting for submitted claim...";
  const createdAt = getDate(casePayload, "created_at");
  const updatedAt = getDate(casePayload, "updated_at");
  const runtime = formatRuntime(createdAt, isTerminal ? updatedAt : null, state ? "N/A" : "Loading");

  const verdict =
    getString(investigation, "case_verdict") ??
    getString(certificate, "overall_verdict") ??
    (isFailed ? "failed" : isCompleted ? "unknown" : "running");
  const confidence = getNumber(investigation, "confidence") ?? getNumber(certificate, "confidence");
  const trustIndex = getNumber(certificate, "trust_index");

  return (
    <div className="space-y-6">
      <section className="overflow-hidden border border-slate-800 bg-slate-900/70 shadow-2xl shadow-slate-950/30">
        <div className="h-1 bg-gradient-to-r from-cyan-300 via-emerald-300 to-amber-300" />
        <div className="p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Submitted Claim</p>
            <h1 className="mt-3 max-w-5xl text-3xl font-semibold leading-tight text-white">{submittedClaim}</h1>
            <p className="mt-3 break-all text-xs text-slate-500">{caseId}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/?sample=score" className="inline-flex items-center gap-2 border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-sm text-amber-100 hover:border-amber-200">
              <Route className="h-4 w-4" aria-hidden="true" />
              Try Sample
            </Link>
            <Link href="/" className="inline-flex items-center gap-2 border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-sm text-cyan-100 hover:border-cyan-200">
              <Plus className="h-4 w-4" aria-hidden="true" />
              New Case
            </Link>
            <StatusBadge status={status} />
          </div>
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-5">
          <Metric label="Verdict" value={verdict} tone="emerald" />
          <Metric label="Confidence" value={confidence === null ? "N/A" : confidence.toFixed(3)} tone="cyan" />
          <Metric label="Trust Index" value={trustIndex === null ? "N/A" : trustIndex.toFixed(3)} tone="amber" />
          <Metric label="State" value={status} tone="violet" />
          <Metric label="Runtime" value={runtime} tone="cyan" />
        </div>
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

      <div className="grid gap-6 lg:grid-cols-[1.35fr_0.65fr]">
        <Panel title="Evidence Graph">
          <EvidenceGraphVisualizer graph={graph} />
        </Panel>

        <Panel title="Verdict Summary">
          <KeyValue label="Verdict" value={verdict} icon={<ShieldCheck className="h-4 w-4 text-emerald-300" />} />
          <KeyValue label="Confidence" value={confidence === null ? "N/A" : confidence.toFixed(3)} icon={<Gauge className="h-4 w-4 text-cyan-300" />} />
          <KeyValue label="Trust Index" value={trustIndex === null ? "N/A" : trustIndex.toFixed(3)} icon={<Fingerprint className="h-4 w-4 text-amber-300" />} />
          <KeyValue label="Nodes" value={String(asArray(graph?.nodes).length)} />
          <KeyValue label="Links" value={String(asArray(graph?.edges).length)} />
          <KeyValue label="Runtime" value={runtime} icon={<Clock className="h-4 w-4 text-violet-300" />} />
        </Panel>
      </div>

      <PlannerPanel runs={plannerRuns} />

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
    </div>
  );
}

function PlannerPanel({ runs }: { runs: unknown[] }) {
  const records = runs.filter(isRecord);
  return (
    <Panel title="AI Planner">
      {records.length === 0 ? (
        <EmptyText>Planner output is not available yet.</EmptyText>
      ) : (
        records.map((run, index) => {
          const metadata = isRecord(run.metadata) ? run.metadata : {};
          const queries = asArray(metadata.queries).filter(isRecord);
          const candidates = asArray(metadata.source_candidates).filter(isRecord);
          return (
            <div key={getString(run, "agent_run_id") ?? index} className="border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm font-semibold text-white">{getString(run, "agent_name") ?? "Planner"}</p>
                <span className="text-xs text-slate-500">{getString(run, "provider") ?? "internal"}</span>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <div>
                  <p className="text-xs uppercase text-slate-500">Queries</p>
                  <div className="mt-2 space-y-2">
                    {queries.length === 0 ? (
                      <p className="text-sm text-slate-400">{getString(run, "output_summary") ?? "No query details recorded."}</p>
                    ) : (
                      queries.map((query, queryIndex) => (
                        <div key={queryIndex} className="border border-slate-800 bg-slate-900/70 px-3 py-2">
                          <p className="text-sm text-slate-100">{getString(query, "query") ?? "Unnamed query"}</p>
                          <p className="mt-1 text-xs text-slate-500">{getString(query, "purpose") ?? getString(query, "provider") ?? "planner query"}</p>
                          <PlannerChips values={asStringArray(query.validation_terms)} tone="cyan" />
                          <PlannerChips values={asStringArray(query.target_domains)} tone="slate" />
                        </div>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-xs uppercase text-slate-500">Source Candidates</p>
                  <div className="mt-2 space-y-2">
                    {candidates.length === 0 ? (
                      <p className="text-sm text-slate-400">No direct source candidates recorded.</p>
                    ) : (
                      candidates.map((candidate, candidateIndex) => (
                        <div key={candidateIndex} className="border border-slate-800 bg-slate-900/70 px-3 py-2">
                          <p className="text-sm text-slate-100">{getString(candidate, "name") ?? getString(candidate, "domain") ?? "Source candidate"}</p>
                          <p className="mt-1 text-xs text-slate-500">{getString(candidate, "url") ?? getString(candidate, "rationale") ?? "planner source"}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                            <span className="border border-slate-700 bg-slate-950 px-2 py-1">
                              confidence {formatConfidence(getNumber(candidate, "source_confidence"))}
                            </span>
                            <span className="border border-slate-700 bg-slate-950 px-2 py-1">
                              {getString(candidate, "confidence_source") ?? "planner"}
                            </span>
                            <span className="border border-slate-700 bg-slate-950 px-2 py-1">
                              {getString(candidate, "domain") ?? "unknown domain"}
                            </span>
                          </div>
                          <PlannerChips values={asStringArray(candidate.validation_terms)} tone="emerald" />
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })
      )}
    </Panel>
  );
}

function formatConfidence(value: number | null) {
  if (value === null) return "n/a";
  return value.toFixed(2);
}

function PlannerChips({ values, tone }: { values: string[]; tone: "cyan" | "emerald" | "slate" }) {
  if (values.length === 0) return null;

  const toneClass = {
    cyan: "border-cyan-400/30 bg-cyan-500/10 text-cyan-100",
    emerald: "border-emerald-400/30 bg-emerald-500/10 text-emerald-100",
    slate: "border-slate-700 bg-slate-950 text-slate-300",
  }[tone];

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {values.slice(0, 5).map((value) => (
        <span key={value} className={`border px-2 py-1 text-xs ${toneClass}`}>
          {value}
        </span>
      ))}
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

function Metric({ label, value, tone }: { label: string; value: string; tone: "emerald" | "cyan" | "amber" | "violet" }) {
  const toneClass = {
    emerald: "from-emerald-400/15 text-emerald-100",
    cyan: "from-cyan-400/15 text-cyan-100",
    amber: "from-amber-400/15 text-amber-100",
    violet: "from-violet-400/15 text-violet-100",
  }[tone];

  return (
    <div className={`border border-slate-800 bg-gradient-to-br ${toneClass} to-slate-950 p-4`}>
      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-white">{value}</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border border-slate-800 bg-slate-900/55 shadow-xl shadow-slate-950/20">
      <div className="border-b border-slate-800 bg-slate-950/35 px-5 py-4">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
      </div>
      <div className="space-y-3 p-5">{children}</div>
    </section>
  );
}

function KeyValue({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 bg-slate-950/60 px-4 py-3">
      <span className="inline-flex items-center gap-2 text-sm text-slate-400">
        {icon}
        {label}
      </span>
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
