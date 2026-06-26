import type { FailureCase } from "../lib/schema";

export function FailureDetail({ failure }: { failure?: FailureCase }) {
  return (
    <aside className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel" aria-live="polite">
      <p className="font-mono text-xs uppercase text-signal-700">Failure detail</p>
      {!failure ? (
        <p className="mt-4 text-sm text-ink-600">Select a failure case to inspect its evidence.</p>
      ) : (
        <div className="mt-3 space-y-5">
          <div>
            <h2 className="text-lg font-semibold">{failure.caseId}</h2>
            <p className="mt-1 text-sm leading-6 text-ink-600">{failure.reason}</p>
          </div>
          {failure.interpretation ? (
            <div className="rounded-md bg-canvas p-3">
              <h3 className="text-xs font-semibold uppercase text-ink-600">
                Provider interpretation
              </h3>
              <p className="mt-2 text-sm leading-6">{failure.interpretation}</p>
            </div>
          ) : null}
          <DetailList label="Expected" values={failure.expectedIds} />
          <DetailList label="Retrieved" values={failure.retrievedIds} />
          <DetailList label="Included" values={failure.includedIds} />
          <DetailList label="Excluded" values={failure.excludedIds} />
          <DetailList label="Trace IDs" values={failure.traceIds} />
          <div>
            <h3 className="text-xs font-semibold uppercase text-ink-600">Suggested action</h3>
            <p className="mt-2 text-sm leading-6">{failure.suggestedAction}</p>
          </div>
        </div>
      )}
    </aside>
  );
}

function DetailList({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase text-ink-600">{label}</h3>
      <p className="mt-2 break-words font-mono text-xs leading-5">
        {values.length ? values.join(", ") : "none"}
      </p>
    </div>
  );
}
