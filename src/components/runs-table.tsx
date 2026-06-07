import type { BenchmarkRun, RunStatus } from "../lib/schema";

const statusStyles: Record<RunStatus, string> = {
  pending: "bg-slate-100 text-slate-700",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  skipped: "bg-amber-100 text-amber-900",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusStyles[status]}`}
    >
      {status}
    </span>
  );
}

export function RunsTable({ runs }: { runs: BenchmarkRun[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-ink-950/10 bg-white shadow-panel">
      <table className="w-full min-w-[720px] border-collapse text-left">
        <caption className="sr-only">Local benchmark runs</caption>
        <thead>
          <tr className="border-b border-ink-950/10 bg-canvas/70 text-xs uppercase text-ink-600">
            <th className="px-5 py-3 font-semibold">Run</th>
            <th className="px-5 py-3 font-semibold">Suite</th>
            <th className="px-5 py-3 font-semibold">Cases</th>
            <th className="px-5 py-3 font-semibold">Run status</th>
            <th className="px-5 py-3 font-semibold">Mneno</th>
            <th className="px-5 py-3 font-semibold">Source</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-b border-ink-950/10 last:border-0">
              <td className="px-5 py-4">
                <p className="font-mono text-sm font-medium text-ink-950">{run.id}</p>
                <p className="mt-1 text-xs text-ink-600">{run.startedAt}</p>
              </td>
              <td className="px-5 py-4 text-sm">{run.suite}</td>
              <td className="px-5 py-4 font-mono text-sm tabular-nums">{run.cases}</td>
              <td className="px-5 py-4">
                <StatusBadge status={run.status} />
              </td>
              <td className="px-5 py-4">
                <StatusBadge status={run.mnenoStatus} />
              </td>
              <td className="px-5 py-4 text-sm capitalize text-ink-600">
                {run.source}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
