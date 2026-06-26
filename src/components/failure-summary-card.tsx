import { AlertTriangle, Layers3, Users } from "lucide-react";

import type { RootCauseSummary } from "../lib/schema";

export function FailureSummaryCard({
  summary,
  viewLabel,
}: {
  summary: RootCauseSummary;
  viewLabel: string;
}) {
  const topCategory = Object.entries(summary.byCategory).sort(
    (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
  )[0];
  const severe =
    (summary.bySeverity.critical ?? 0) + (summary.bySeverity.high ?? 0);

  return (
    <section aria-labelledby="failure-summary-heading" className="grid gap-4 md:grid-cols-3">
      <div className="rounded-lg border border-red-200 bg-white p-4 shadow-panel">
        <div className="flex items-center gap-2 text-red-700">
          <AlertTriangle aria-hidden="true" size={18} />
          <h2 id="failure-summary-heading" className="text-xs font-semibold uppercase">
            Total failures
          </h2>
        </div>
        <p className="mt-3 font-mono text-3xl font-semibold tabular-nums">
          {summary.totalFailures}
        </p>
        <p className="mt-1 text-xs text-ink-600">{severe} high or critical</p>
      </div>
      <div className="rounded-lg border border-ink-950/10 bg-white p-4 shadow-panel">
        <div className="flex items-center gap-2 text-ink-600">
          <Layers3 aria-hidden="true" size={18} />
          <p className="text-xs font-semibold uppercase">
            Top category - {viewLabel}
          </p>
        </div>
        <p className="mt-3 text-lg font-semibold">
          {topCategory ? formatLabel(topCategory[0]) : "None"}
        </p>
        <p className="mt-1 font-mono text-xs text-ink-600">
          {topCategory?.[1] ?? 0} classifications
        </p>
      </div>
      <div className="rounded-lg border border-ink-950/10 bg-white p-4 shadow-panel">
        <div className="flex items-center gap-2 text-ink-600">
          <Users aria-hidden="true" size={18} />
          <p className="text-xs font-semibold uppercase">Providers</p>
        </div>
        <p className="mt-3 font-mono text-3xl font-semibold tabular-nums">
          {Object.keys(summary.byProvider).length}
        </p>
        <p className="mt-1 text-xs text-ink-600">{viewLabel}</p>
      </div>
    </section>
  );
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
