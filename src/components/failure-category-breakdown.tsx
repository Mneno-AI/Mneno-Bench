import type { RootCauseSummary } from "../lib/schema";

export function FailureCategoryBreakdown({
  summary,
}: {
  summary: RootCauseSummary;
}) {
  const entries = Object.entries(summary.byCategory).sort(
    (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
  );
  const maximum = Math.max(1, ...entries.map(([, count]) => count));

  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <p className="font-mono text-xs uppercase text-signal-700">Root causes</p>
      <h2 className="mt-1 text-lg font-semibold">Failure category breakdown</h2>
      {entries.length ? (
        <ul className="mt-5 space-y-4">
          {entries.map(([category, count]) => (
            <li key={category}>
              <div className="flex items-center justify-between gap-4 text-sm">
                <span className="font-medium">{formatLabel(category)}</span>
                <span className="font-mono tabular-nums text-ink-600">{count}</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-canvas" aria-hidden="true">
                <div
                  className="h-full rounded-full bg-signal-600"
                  style={{ width: `${Math.max(6, (count / maximum) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-ink-600">No failure categories were recorded.</p>
      )}
    </section>
  );
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
