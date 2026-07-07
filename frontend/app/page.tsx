import Link from "next/link";
import { VerificationComposer } from "@/components/VerificationComposer";

const capabilities = [
  "Atomic claim decomposition",
  "Evidence retrieval",
  "LLM stance classification",
  "PIVOT verdict scoring",
  "Trust Certificate output",
  "Audit and cost logs",
];

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <section className="mx-auto flex min-h-screen max-w-7xl flex-col px-6 py-8 md:px-10">
        <nav className="flex items-center justify-between border-b border-slate-800 pb-5">
          <Link href="/" className="text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">DeltaMind</Link>
          <Link href="/dashboard" className="border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-cyan-300">Dashboard</Link>
        </nav>

        <div className="grid flex-1 items-center gap-10 py-12 lg:grid-cols-[0.9fr_1.1fr]">
          <section>
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-emerald-300">Investigation Engine</p>
            <h1 className="mt-5 max-w-4xl text-5xl font-semibold leading-tight text-white md:text-6xl">Verify claims with evidence you can inspect.</h1>
            <p className="mt-6 max-w-2xl text-base leading-8 text-slate-300">DeltaMind turns a short claim or long report into a backend investigation, then streams the case state into a live result page with verdicts, evidence, corrections, graph summaries, and a Trust Certificate.</p>
            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {capabilities.map((item) => (
                <div key={item} className="border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm text-slate-200">{item}</div>
              ))}
            </div>
          </section>
          <VerificationComposer />
        </div>
      </section>
    </main>
  );
}
