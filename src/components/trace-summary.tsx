import type { TraceSummary as TraceSummaryType } from "../lib/schema";

export function TraceSummary({ trace }: { trace: TraceSummaryType }) {
  const values = [
    ["Operations", trace.operations],
    ["Events", trace.events],
    ["Decisions", trace.decisions],
    ["Retrieved", trace.retrieved],
    ["Selected", trace.selected],
    ["Suppressed", trace.suppressed],
    ["Conflicts resolved", trace.conflictsResolved],
    ["Explanations", trace.explanations],
  ];

  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <p className="font-mono text-xs uppercase text-ink-600">Trace summary</p>
      <div className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-ink-950/10 bg-ink-950/10 sm:grid-cols-4">
        {values.map(([label, value]) => (
          <div key={label} className="bg-white p-4">
            <p className="font-mono text-2xl font-semibold tabular-nums">{value}</p>
            <p className="mt-1 text-xs leading-5 text-ink-600">{label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
