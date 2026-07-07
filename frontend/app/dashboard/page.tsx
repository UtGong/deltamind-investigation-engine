import Link from "next/link";
import { getDashboardSummary } from "@/lib/api";

export default async function DashboardPage() {
  let summary = null;
  let error = null;

  try {
    summary = await getDashboardSummary();
  } catch (requestError) {
    error = requestError instanceof Error ? requestError.message : "Dashboard failed to load.";
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-white md:px-10">
      <div className="mx-auto max-w-6xl">
        <nav className="mb-8 flex items-center justify-between border-b border-slate-800 pb-5">
          <Link href="/" className="text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">DeltaMind</Link>
          <Link href="/" className="border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-cyan-300">New Case</Link>
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
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-slate-800 bg-slate-900/70 p-5">
      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-white">{value}</p>
    </div>
  );
}
