import { CircleAlert } from "lucide-react";

import type { BenchmarkRun } from "../lib/schema";
import { StatusBadge } from "./runs-table";

export function ResultDetail({ run }: { run: BenchmarkRun }) {
  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase text-ink-600">Selected run</p>
          <h2 className="mt-1 text-lg font-semibold">{run.id}</h2>
        </div>
        <StatusBadge status={run.status} />
      </div>
      <dl className="mt-5 grid gap-4 border-t border-ink-950/10 pt-5 sm:grid-cols-4">
        <div>
          <dt className="text-xs uppercase text-ink-600">Cases</dt>
          <dd className="mt-1 font-mono text-sm font-semibold">{run.cases}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-ink-600">Systems</dt>
          <dd className="mt-1 text-sm font-semibold">{run.systems.join(", ")}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-ink-600">Bench version</dt>
          <dd className="mt-1 font-mono text-sm font-semibold">
            {run.benchmarkVersion}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-ink-600">Mneno version</dt>
          <dd className="mt-1 font-mono text-sm font-semibold">
            {run.mnenoVersion ?? "Not installed"}
          </dd>
        </div>
      </dl>
      <div className="mt-5 flex gap-3 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
        <CircleAlert className="mt-0.5 shrink-0" aria-hidden="true" size={18} />
        <p>
          This is a synthetic development run. A skipped Mneno status means the
          optional SDK was not installed; no score was fabricated.
        </p>
      </div>
    </section>
  );
}
