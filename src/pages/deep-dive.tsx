import { useState } from "react";

import { retrievalDeepDives } from "../lib/runs";
import type {
  CountPercentage,
  RetrievalDeepDive,
  RetrievalFailureInspection,
} from "../lib/schema";
import { PageHeader } from "./dashboard";

export function DeepDivePage({
  reports = retrievalDeepDives,
}: {
  reports?: RetrievalDeepDive[];
}) {
  const report = reports[0];
  const providers = report
    ? Array.from(new Set(report.sampledFailures.map((item) => item.provider))).sort()
    : [];
  const rootCauses = report ? Object.keys(report.rootCauses) : [];
  const [provider, setProvider] = useState("all");
  const [rootCause, setRootCause] = useState("all");
  const filtered = report
    ? filterDeepDiveFailures(report.sampledFailures, provider, rootCause)
    : [];
  const [selectedId, setSelectedId] = useState("");
  const selected =
    filtered.find((item) => item.id === selectedId) ?? filtered[0] ?? null;

  return (
    <>
      <PageHeader
        eyebrow="Diagnostics only"
        title="Retrieval Deep Dive"
        description="Inspect candidate generation, ranking, session bias, budget decisions, and unknowns using preserved LOCOMO evidence before changing Mneno Core."
      />
      {!report ? (
        <EmptyState />
      ) : (
        <div className="space-y-6">
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Retrieval failures" value={String(report.totalFailures)} />
            <StatCard label="Sampled failures" value={String(report.statistics.sampleSize)} />
            <StatCard label="Retrieval recall" value={formatRatio(report.statistics.retrievalRecall)} />
            <StatCard label="Candidate coverage" value={formatRatio(report.statistics.candidateCoverage)} />
          </section>

          <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
            <div className="grid gap-4 sm:grid-cols-2">
              <Filter
                id="provider-filter"
                label="Provider"
                value={provider}
                options={["all", ...providers]}
                onChange={(value) => {
                  setProvider(value);
                  setSelectedId("");
                }}
              />
              <Filter
                id="root-cause-filter"
                label="Root cause"
                value={rootCause}
                options={["all", ...rootCauses]}
                onChange={(value) => {
                  setRootCause(value);
                  setSelectedId("");
                }}
              />
            </div>
            <p className="mt-4 text-sm leading-6 text-ink-600">
              Showing {filtered.length} of {report.sampledFailures.length} sampled failures.
              Unknown remains visible when the artifacts do not support a narrower cause.
            </p>
          </section>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,0.8fr)]">
            <RootCauseDistribution values={report.rootCauses} />
            <QuestionTypeStatistics values={report.statistics.failuresByQuestionType} />
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)]">
            <FailureSamples
              failures={filtered}
              selectedId={selected?.id}
              onSelect={setSelectedId}
            />
            <FailureEvidence failure={selected} />
          </div>

          <ImprovementOpportunities report={report} />
        </div>
      )}
    </>
  );
}

export function filterDeepDiveFailures(
  failures: RetrievalFailureInspection[],
  provider: string,
  rootCause: string,
) {
  return failures.filter(
    (failure) =>
      (provider === "all" || failure.provider === provider) &&
      (rootCause === "all" || failure.rootCause === rootCause),
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-4 shadow-panel">
      <p className="text-xs uppercase text-ink-600">{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">{value}</p>
    </section>
  );
}

function Filter({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="text-sm font-semibold" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 min-h-11 w-full rounded-md border border-ink-950/15 bg-white px-3 text-sm focus:border-signal-700 focus:outline-none focus:ring-2 focus:ring-signal-100"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {formatLabel(option)}
          </option>
        ))}
      </select>
    </div>
  );
}

function RootCauseDistribution({
  values,
}: {
  values: Record<string, CountPercentage>;
}) {
  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <p className="font-mono text-xs uppercase text-signal-700">Classification</p>
      <h2 className="mt-1 text-lg font-semibold">Root cause distribution</h2>
      <div className="mt-5 space-y-4">
        {Object.entries(values).map(([cause, value]) => (
          <div key={cause}>
            <div className="flex items-center justify-between gap-4 text-sm">
              <span className="font-medium">{formatLabel(cause)}</span>
              <span className="font-mono tabular-nums text-ink-600">
                {value.count} / {value.percentage.toFixed(1)}%
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-signal-700"
                style={{ width: `${Math.max(value.percentage, 1)}%` }}
                role="img"
                aria-label={`${formatLabel(cause)}: ${value.percentage.toFixed(1)} percent`}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function QuestionTypeStatistics({
  values,
}: {
  values: Record<string, CountPercentage>;
}) {
  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <p className="font-mono text-xs uppercase text-signal-700">Sample coverage</p>
      <h2 className="mt-1 text-lg font-semibold">Question types</h2>
      <dl className="mt-4 divide-y divide-ink-950/10">
        {Object.entries(values).map(([type, value]) => (
          <div key={type} className="flex items-center justify-between gap-4 py-3">
            <dt className="text-sm text-ink-600">{formatLabel(type)}</dt>
            <dd className="font-mono text-sm font-semibold tabular-nums">
              {value.count} ({value.percentage.toFixed(1)}%)
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function FailureSamples({
  failures,
  selectedId,
  onSelect,
}: {
  failures: RetrievalFailureInspection[];
  selectedId?: string;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-panel">
      <div className="border-b border-ink-950/10 p-5">
        <p className="font-mono text-xs uppercase text-signal-700">Evidence sample</p>
        <h2 className="mt-1 text-lg font-semibold">Failure samples</h2>
      </div>
      {failures.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-canvas text-xs uppercase text-ink-600">
              <tr>
                <th className="px-4 py-3 font-medium">Case</th>
                <th className="px-4 py-3 font-medium">Question type</th>
                <th className="px-4 py-3 font-medium">Root cause</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-950/10">
              {failures.map((failure) => (
                <tr key={failure.id} className={selectedId === failure.id ? "bg-signal-100/60" : ""}>
                  <td className="p-0">
                    <button
                      type="button"
                      onClick={() => onSelect(failure.id)}
                      className="min-h-11 w-full cursor-pointer px-4 py-3 text-left font-mono text-xs font-semibold text-signal-700 hover:underline"
                    >
                      {failure.caseId}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-ink-600">{formatLabel(failure.questionType)}</td>
                  <td className="px-4 py-3 font-medium">{formatLabel(failure.rootCause)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-5 text-sm text-ink-600">No failures match the selected filters.</p>
      )}
    </section>
  );
}

function FailureEvidence({ failure }: { failure: RetrievalFailureInspection | null }) {
  if (!failure) {
    return (
      <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
        <h2 className="text-lg font-semibold">Failure evidence</h2>
        <p className="mt-3 text-sm text-ink-600">Select a failure to inspect its evidence.</p>
      </section>
    );
  }
  const selected = failure.retrievedCandidates.filter((item) => item.selected);
  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <p className="font-mono text-xs uppercase text-signal-700">{failure.caseId}</p>
      <h2 className="mt-1 text-lg font-semibold">{formatLabel(failure.rootCause)}</h2>
      <p className="mt-3 text-sm leading-6 text-ink-600">{failure.explanation}</p>
      <EvidenceBlock title="Question" values={[failure.question, `Normalized: ${failure.normalizedQuestion}`]} />
      <EvidenceBlock
        title="Expected evidence"
        values={failure.expectedEvidence.map(
          (item) => `${item.evidenceId}: ${item.text ?? "text unavailable"}`,
        )}
      />
      <EvidenceBlock
        title="Retrieved evidence"
        values={selected.map(
          (item) => `${item.id}: ${item.text ?? "text unavailable"}${item.score === null ? "" : ` (score ${item.score.toFixed(4)})`}`,
        )}
      />
      <EvidenceBlock title="Trace IDs" values={failure.traceIds} mono />
      <EvidenceBlock title="Classification evidence" values={failure.classificationEvidence} mono />
    </section>
  );
}

function EvidenceBlock({
  title,
  values,
  mono = false,
}: {
  title: string;
  values: string[];
  mono?: boolean;
}) {
  return (
    <div className="mt-5 border-t border-ink-950/10 pt-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      {values.length ? (
        <ul className={`mt-2 space-y-2 text-sm leading-6 text-ink-600 ${mono ? "font-mono text-xs" : ""}`}>
          {values.map((value, index) => (
            <li key={`${value}-${index}`} className="break-words">{value}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-ink-600">None recorded.</p>
      )}
    </div>
  );
}

function ImprovementOpportunities({ report }: { report: RetrievalDeepDive }) {
  return (
    <section>
      <p className="font-mono text-xs uppercase text-signal-700">Evidence to action</p>
      <h2 className="mt-1 text-xl font-semibold">Improvement opportunities</h2>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {report.recommendations.map((opportunity) => (
          <article key={opportunity.title} className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <h3 className="font-semibold">{opportunity.title}</h3>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
                {formatLabel(opportunity.confidence)} confidence
              </span>
            </div>
            <p className="mt-3 text-sm leading-6 text-ink-600">{opportunity.expectedImpact}</p>
            <p className="mt-3 text-sm"><strong>Core area:</strong> {opportunity.suggestedCoreArea}</p>
            <ul className="mt-3 space-y-2 font-mono text-xs leading-5 text-ink-600">
              {opportunity.evidence.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function EmptyState() {
  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <h2 className="text-lg font-semibold">No retrieval deep dive found</h2>
      <p className="mt-2 text-sm leading-6 text-ink-600">
        Run <code className="font-mono">python -m benchmarks.locomo.deep_dive</code> after a LOCOMO run.
      </p>
    </section>
  );
}

function formatRatio(value: number | null) {
  return value === null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
}

function formatLabel(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
