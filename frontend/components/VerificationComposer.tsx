"use client";

import { FileText, Network, Play, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { VerificationMode, VerifyResponse } from "@/types/verification";

const sampleClaims: Record<string, string> = {
  score: "Belgium beats USA with a 3-1 win in the Round of 16",
};

export function VerificationComposer() {
  const router = useRouter();
  const [mode, setMode] = useState<VerificationMode>("claim");
  const [text, setText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const sample = new URLSearchParams(window.location.search).get("sample");
      if (sample && sampleClaims[sample]) {
        setMode("claim");
        setText(sampleClaims[sample]);
        setStatus("Sample loaded");
      }
    }, 0);

    return () => window.clearTimeout(timer);
  }, []);

  async function submit() {
    setError(null);
    if (!text.trim()) {
      setError("Enter a claim or report before starting verification.");
      return;
    }

    setIsSubmitting(true);
    setStatus("Creating case");

    try {
      const response = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, text }),
      });
      const payload = (await response.json()) as VerifyResponse;

      if (!response.ok || !payload.case_id) {
        throw new Error(payload.error ?? "Verification failed to start.");
      }

      setStatus("Opening live result");
      router.push(`/cases/${payload.case_id}`);
    } catch (requestError) {
      setStatus("Failed");
      setError(requestError instanceof Error ? requestError.message : "Verification failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="overflow-hidden border border-slate-700 bg-slate-950/80 shadow-2xl shadow-slate-950/40 backdrop-blur md:p-0">
      <div className="h-1 bg-gradient-to-r from-cyan-300 via-emerald-300 to-amber-300" />
      <div className="p-5 md:p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Investigation Console</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Submit a claim or report</h2>
        </div>
        <div className="grid h-11 w-11 place-items-center border border-emerald-300/30 bg-emerald-300/10">
          <ShieldCheck className="h-6 w-6 text-emerald-300" aria-hidden="true" />
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-2 bg-slate-900/90 p-1">
        <button
          type="button"
          onClick={() => setMode("claim")}
          className={mode === "claim" ? "bg-white px-4 py-3 text-sm font-semibold text-slate-950" : "px-4 py-3 text-sm text-slate-300 hover:bg-slate-800 hover:text-white"}
        >
          Single Claim
        </button>
        <button
          type="button"
          onClick={() => setMode("report")}
          className={mode === "report" ? "bg-white px-4 py-3 text-sm font-semibold text-slate-950" : "px-4 py-3 text-sm text-slate-300 hover:bg-slate-800 hover:text-white"}
        >
          Full Report
        </button>
      </div>

      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={mode === "claim" ? "Enter one factual claim to investigate..." : "Paste a longer report or article text..."}
        className="mt-4 min-h-72 w-full resize-y border border-slate-700 bg-slate-950/90 p-4 text-sm leading-7 text-white outline-none placeholder:text-slate-500 focus:border-cyan-300 focus:ring-2 focus:ring-cyan-300/15"
      />

      <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <FileText className="h-4 w-4" aria-hidden="true" />
          <span>{status}</span>
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={isSubmitting}
          className="inline-flex items-center justify-center gap-2 bg-cyan-300 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-950/40 hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Play className="h-4 w-4" aria-hidden="true" />
          {isSubmitting ? "Starting" : "Run Verification"}
        </button>
      </div>

      {error && <div className="mt-4 border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-100">{error}</div>}
      </div>
      <div className="border-t border-slate-800 bg-slate-900/60 px-5 py-4 md:px-6">
        <div className="flex items-center gap-2 text-sm text-slate-300">
          <Network className="h-4 w-4 text-amber-300" aria-hidden="true" />
          Claims &gt; evidence &gt; sources
        </div>
      </div>
    </section>
  );
}
