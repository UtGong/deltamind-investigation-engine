import Link from "next/link";
import { CaseResultPoller } from "@/components/CaseResultPoller";

type PageProps = { params: Promise<{ caseId: string }> };

export default async function CasePage({ params }: PageProps) {
  const { caseId } = await params;
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#164e63_0,#0f172a_32%,#020617_76%)] px-6 py-8 text-white md:px-10">
      <div className="mx-auto max-w-7xl">
        <nav className="mb-8 flex items-center justify-between border-b border-slate-800 pb-5">
          <Link href="/" className="text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">DeltaMind</Link>
          <Link href="/dashboard" className="border border-slate-700 bg-slate-950/40 px-4 py-2 text-sm text-slate-200 hover:border-cyan-300">Dashboard</Link>
        </nav>
        <CaseResultPoller caseId={caseId} />
      </div>
    </main>
  );
}
