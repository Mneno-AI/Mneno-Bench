import { useState } from "react";

import { FailureCategoryBreakdown } from "../components/failure-category-breakdown";
import { FailureDetail } from "../components/failure-detail";
import { FailureSummaryCard } from "../components/failure-summary-card";
import { FailureTable } from "../components/failure-table";
import {
  emptySummary,
  filterFailuresByProvider,
  summaryForProvider,
  type ProviderFilter,
} from "../lib/failure-filters";
import { failureReports } from "../lib/runs";
import type { FailureCase, FailureReport } from "../lib/schema";
import { PageHeader } from "./dashboard";

const providerTabs: Array<{ id: ProviderFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "mneno", label: "Mneno" },
  { id: "keyword_baseline", label: "Keyword" },
  { id: "full_context_baseline", label: "Full Context" },
  { id: "random_baseline", label: "Random" },
];

export function FailuresPage({ reports = failureReports }: { reports?: FailureReport[] }) {
  const [reportId, setReportId] = useState(reports[0]?.id ?? "");
  const [providerFilter, setProviderFilter] = useState<ProviderFilter>("all");
  const report = reports.find((item) => item.id === reportId) ?? reports[0];
  const filteredFailures = report
    ? filterFailuresByProvider(report.failures, providerFilter)
    : [];
  const orderedFailures = worstFailures(filteredFailures);
  const activeSummary = report
    ? summaryForProvider(report, providerFilter)
    : emptySummary();
  const [selectedId, setSelectedId] = useState(orderedFailures[0]?.id ?? "");
  const selected = orderedFailures.find((failure) => failure.id === selectedId) ?? orderedFailures[0];

  const selectReport = (nextReport: FailureReport) => {
    setReportId(nextReport.id);
    setProviderFilter("all");
    setSelectedId(worstFailures(nextReport.failures)[0]?.id ?? "");
  };

  const selectProvider = (provider: ProviderFilter) => {
    setProviderFilter(provider);
    const nextFailures = report
      ? worstFailures(filterFailuresByProvider(report.failures, provider))
      : [];
    setSelectedId(nextFailures[0]?.id ?? "");
  };

  return (
    <>
      <PageHeader
        eyebrow="Evidence-based diagnosis"
        title="Failure Analysis"
        description="Scores show performance. Failure analysis links observed problems to retrieval, ranking, lifecycle, session, conflict, compaction, answer, judge, or dataset evidence without inventing root causes."
      />
      {!report ? (
        <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
          <h2 className="text-lg font-semibold">No failure report found</h2>
          <p className="mt-2 text-sm leading-6 text-ink-600">
            Run the Mneno Context Rot Suite or LOCOMO runner to generate local failure JSON reports.
          </p>
        </section>
      ) : (
        <div className="space-y-6">
          {reports.length > 1 ? (
            <nav aria-label="Failure reports" className="flex flex-wrap gap-2">
              {reports.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-current={item.id === report.id ? "page" : undefined}
                  onClick={() => selectReport(item)}
                  className={`min-h-11 cursor-pointer rounded-md px-4 text-sm font-semibold transition-colors ${
                    item.id === report.id
                      ? "bg-ink-950 text-white"
                      : "border border-ink-950/10 bg-white text-ink-600 hover:bg-canvas"
                  }`}
                >
                  {formatLabel(item.benchmark)}
                </button>
              ))}
            </nav>
          ) : null}
          <nav aria-label="Provider filter" className="flex flex-wrap gap-2">
            {providerTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                aria-pressed={providerFilter === tab.id}
                onClick={() => selectProvider(tab.id)}
                className={`min-h-11 cursor-pointer rounded-full px-4 text-sm font-semibold transition-colors ${
                  providerFilter === tab.id
                    ? "bg-signal-700 text-white"
                    : "border border-ink-950/10 bg-white text-ink-600 hover:bg-canvas"
                }`}
              >
                {tab.label}
                <span className="ml-2 font-mono text-xs tabular-nums">
                  {summaryForProvider(report, tab.id).totalFailures}
                </span>
              </button>
            ))}
          </nav>
          <ProviderNote provider={providerFilter} />
          <FailureSummaryCard
            summary={activeSummary}
            viewLabel={`${providerLabel(providerFilter)} view`}
          />
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">
            <FailureCategoryBreakdown summary={activeSummary} />
            <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
              <p className="font-mono text-xs uppercase text-signal-700">Suggested actions</p>
              <h2 className="mt-1 text-lg font-semibold">Highest-frequency actions</h2>
              {activeSummary.topSuggestedActions.length ? (
                <ol className="mt-4 list-decimal space-y-3 pl-5 text-sm leading-6 text-ink-600">
                  {activeSummary.topSuggestedActions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ol>
              ) : (
                <p className="mt-4 text-sm text-ink-600">No suggested actions were generated.</p>
              )}
            </section>
          </div>
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,0.7fr)]">
            <FailureTable failures={orderedFailures.slice(0, 10)} selectedId={selected?.id} onSelect={setSelectedFailure} />
            <FailureDetail failure={selected} />
          </div>
        </div>
      )}
    </>
  );

  function setSelectedFailure(failure: FailureCase) {
    setSelectedId(failure.id);
  }
}

function worstFailures(failures: FailureCase[]): FailureCase[] {
  const severity = { critical: 0, high: 1, medium: 2, low: 3 };
  return [...failures].sort(
    (left, right) =>
      severity[left.severity] - severity[right.severity] ||
      left.caseId.localeCompare(right.caseId) ||
      left.provider.localeCompare(right.provider),
  );
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function providerLabel(provider: ProviderFilter): string {
  return providerTabs.find((tab) => tab.id === provider)?.label ?? "All";
}

function ProviderNote({ provider }: { provider: ProviderFilter }) {
  const notes: Record<ProviderFilter, string> = {
    all: "This view combines Mneno and baseline comparison evidence. Use a provider tab before drawing product root-cause conclusions.",
    mneno: "Mneno failures are candidates for Mneno Core investigation and improvement.",
    full_context_baseline:
      "Full Context intentionally includes everything. Forbidden or stale-memory failures are expected comparison evidence, not necessarily bugs.",
    random_baseline:
      "Random retrieval failures are expected baseline behavior and provide a lower-bound comparison.",
    keyword_baseline:
      "Keyword retrieval and session failures reflect known lexical and session-awareness limitations.",
  };
  const note = notes[provider];
  return (
    <section className="rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm leading-6 text-sky-950">
      <strong>{providerLabel(provider)} interpretation:</strong> {note}
    </section>
  );
}
