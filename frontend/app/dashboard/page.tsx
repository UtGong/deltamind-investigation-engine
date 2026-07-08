import Link from "next/link";
import { getCases, getDashboardSummary } from "@/lib/api";
import type { CaseSummary, DashboardSummary } from "@/lib/api";

export default async function DashboardPage() {
  let summary: DashboardSummary | null = null;
  let cases: CaseSummary[] = [];
  let error = null;

  try {
    [summary, cases] = await Promise.all([getDashboardSummary(), getCases()]);
  } catch (requestError) {
    error = requestError instanceof Error ? requestError.message : "Dashboard failed to load.";
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#164e63_0,#0f172a_32%,#020617_76%)] px-6 py-8 text-white md:px-10">
      <div className="mx-auto max-w-6xl">
        <nav className="mb-8 flex items-center justify-between border-b border-slate-800 pb-5">
          <Link href="/" className="text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">DeltaMind</Link>
          <Link href="/" className="border border-slate-700 bg-slate-950/40 px-4 py-2 text-sm text-slate-200 hover:border-cyan-300">New Case</Link>
        </nav>
        <h1 className="text-3xl font-semibold">Trust Dashboard</h1>
        <p className="mt-3 text-sm leading-7 text-slate-400">Recent Trust Certificate registry health from the backend.</p>
        {error ? (
          <section className="mt-8 border border-rose-400/30 bg-rose-500/10 p-5 text-sm text-rose-100">{error}</section>
        ) : (
          <section className="mt-8 grid gap-4 md:grid-cols-4">
            <Metric label="Certificates" value={String(summary?.certificate_count ?? 0)} />
            <Metric label="Active" value={String(summary?.active_count ?? 0)} />
            <Metric label="Needs Review" value={String(summary?.review_required_count ?? 0)} />
            <Metric label="Avg Trust" value={(summary?.average_trust_index ?? 0).toFixed(3)} />
          </section>
        )}
        <section className="mt-8 border border-slate-800 bg-slate-900/55 shadow-xl shadow-slate-950/20">
          <div className="border-b border-slate-800 bg-slate-950/35 px-5 py-4">
            <h2 className="text-lg font-semibold text-white">Current Cases</h2>
          </div>
          <div className="divide-y divide-slate-800">
            {cases.length === 0 ? (
              <p className="p-5 text-sm text-slate-400">No cases are currently recorded in the backend case store.</p>
            ) : (
              cases.slice(0, 10).map((item) => (
                <Link key={item.case_id} href={`/cases/${item.case_id}`} className="block px-5 py-4 hover:bg-slate-900">
                  <div className="flex flex-col justify-between gap-2 md:flex-row md:items-start">
                    <div>
                      <p className="text-sm font-medium text-white">{item.input_text}</p>
                      <p className="mt-1 break-all text-xs text-slate-500">{item.case_id}</p>
                    </div>
                    <span className="border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-300">{item.status}</span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-white">{value}</p>
    </div>
  );
}
