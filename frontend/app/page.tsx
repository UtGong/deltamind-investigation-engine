import Link from "next/link";
import { ArrowRight, Atom, FileSearch, GitBranch, ShieldCheck } from "lucide-react";
import { VerificationComposer } from "@/components/VerificationComposer";

const capabilities = [
  { label: "Atomic claims", icon: Atom, tone: "text-cyan-300" },
  { label: "Evidence retrieval", icon: FileSearch, tone: "text-emerald-300" },
  { label: "Linked graph", icon: GitBranch, tone: "text-amber-300" },
  { label: "Trust certificate", icon: ShieldCheck, tone: "text-violet-300" },
];

const previewNodes: Array<{ label: string; x: number; y: number; color: string }> = [
  { label: "Claim", x: 95, y: 88, color: "#2dd4bf" },
  { label: "Evidence", x: 292, y: 86, color: "#93c5fd" },
  { label: "Source", x: 452, y: 78, color: "#fdba74" },
  { label: "Verdict", x: 250, y: 142, color: "#86efac" },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#164e63_0,#0f172a_34%,#020617_72%)] text-white">
      <section className="mx-auto flex min-h-screen max-w-7xl flex-col px-6 py-8 md:px-10">
        <nav className="flex items-center justify-between border-b border-slate-800 pb-5">
          <Link href="/" className="text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">DeltaMind</Link>
          <Link href="/dashboard" className="inline-flex items-center gap-2 border border-slate-700 bg-slate-950/40 px-4 py-2 text-sm text-slate-200 hover:border-cyan-300">
            Dashboard
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </nav>

        <div className="grid flex-1 items-center gap-10 py-12 lg:grid-cols-[0.9fr_1.1fr]">
          <section>
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-emerald-300">Investigation Engine</p>
            <h1 className="mt-5 max-w-4xl text-5xl font-semibold leading-tight text-white md:text-6xl">Verify claims with evidence you can see.</h1>
            <p className="mt-6 max-w-2xl text-base leading-8 text-slate-300">DeltaMind turns a short claim or long report into a backend investigation, then streams the case state into a live result page with verdicts, evidence, corrections, graph summaries, and a Trust Certificate.</p>
            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {capabilities.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} className="flex items-center gap-3 border border-slate-800 bg-slate-900/65 px-4 py-3 text-sm text-slate-200 shadow-lg shadow-slate-950/20">
                    <Icon className={`h-4 w-4 ${item.tone}`} aria-hidden="true" />
                    {item.label}
                  </div>
                );
              })}
            </div>

            <div className="mt-8 border border-slate-800 bg-slate-950/55 p-4 shadow-2xl shadow-slate-950/30">
              <svg viewBox="0 0 520 180" className="h-44 w-full" role="img" aria-label="Investigation network preview">
                <rect width="520" height="180" fill="#020617" />
                <path d="M95 88 C160 20 237 36 292 86 S407 150 452 78" fill="none" stroke="#38bdf8" strokeOpacity="0.42" strokeWidth="2" />
                <path d="M95 88 C168 154 232 148 292 86 S365 28 452 78" fill="none" stroke="#fbbf24" strokeOpacity="0.35" strokeWidth="2" />
                {previewNodes.map((node) => (
                  <g key={node.label} transform={`translate(${node.x} ${node.y})`}>
                    <circle r="26" fill="#0f172a" stroke={node.color} strokeWidth="2" />
                    <text y="4" textAnchor="middle" className="fill-slate-100 text-[10px] font-semibold uppercase">
                      {node.label}
                    </text>
                  </g>
                ))}
              </svg>
            </div>
          </section>
          <VerificationComposer />
        </div>
      </section>
    </main>
  );
}
