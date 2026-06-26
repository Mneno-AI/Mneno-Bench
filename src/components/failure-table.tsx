import type { FailureCase } from "../lib/schema";

interface FailureTableProps {
  failures: FailureCase[];
  selectedId?: string;
  onSelect?: (failure: FailureCase) => void;
}

export function FailureTable({ failures, selectedId, onSelect }: FailureTableProps) {
  return (
    <section className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-panel">
      <div className="border-b border-ink-950/10 p-5">
        <p className="font-mono text-xs uppercase text-signal-700">Worst cases</p>
        <h2 className="mt-1 text-lg font-semibold">Failure cases</h2>
      </div>
      {failures.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-left text-sm">
            <thead className="bg-canvas/70 text-xs uppercase text-ink-600">
              <tr>
                <th className="px-5 py-3 font-semibold">Case</th>
                <th className="px-5 py-3 font-semibold">Provider</th>
                <th className="px-5 py-3 font-semibold">Category</th>
                <th className="px-5 py-3 font-semibold">Severity</th>
                <th className="px-5 py-3 font-semibold">Interpretation</th>
                <th className="px-5 py-3 text-right font-semibold">Traces</th>
                <th className="px-5 py-3 font-semibold">Detail</th>
              </tr>
            </thead>
            <tbody>
              {failures.map((failure) => (
                <tr key={failure.id} className="border-t border-ink-950/10">
                  <td className="px-5 py-4 font-mono text-xs">{failure.caseId}</td>
                  <td className="px-5 py-4 font-medium">{formatLabel(failure.provider)}</td>
                  <td className="px-5 py-4">{formatLabel(failure.category)}</td>
                  <td className="px-5 py-4">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${severityClass(failure.severity)}`}>
                      {failure.severity}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    {failure.expectedBehavior ? (
                      <span className="rounded-full bg-sky-100 px-2.5 py-1 text-xs font-semibold text-sky-800">
                        Expected baseline
                      </span>
                    ) : failure.provider === "mneno" ? (
                      <span className="rounded-full bg-red-100 px-2.5 py-1 text-xs font-semibold text-red-800">
                        Core investigation
                      </span>
                    ) : (
                      <span className="text-xs text-ink-600">Comparison evidence</span>
                    )}
                  </td>
                  <td className="px-5 py-4 text-right font-mono tabular-nums">
                    {failure.traceIds.length}
                  </td>
                  <td className="px-5 py-4">
                    <button
                      type="button"
                      aria-pressed={selectedId === failure.id}
                      onClick={() => onSelect?.(failure)}
                      className="min-h-11 cursor-pointer rounded-md px-3 text-sm font-semibold text-signal-700 transition-colors hover:bg-signal-100"
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-5 text-sm text-ink-600">
          No failures match the selected provider.
        </p>
      )}
    </section>
  );
}

function severityClass(severity: FailureCase["severity"]): string {
  if (severity === "critical") return "bg-red-100 text-red-800";
  if (severity === "high") return "bg-orange-100 text-orange-800";
  if (severity === "medium") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-700";
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
