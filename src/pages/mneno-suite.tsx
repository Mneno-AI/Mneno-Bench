import { FileText, GitCompareArrows, Route, SearchCheck } from "lucide-react";

import { StatusBadge } from "../components/runs-table";
import { latestRun } from "../lib/runs";
import type { BenchmarkRun, ContextRotSystemSummary } from "../lib/schema";
import { PageHeader } from "./dashboard";

const systemLabels: Record<string, string> = {
  keyword_baseline: "Keyword",
  full_context_baseline: "Full context",
  random_baseline: "Random",
  mneno: "Mneno",
};

export function MnenoSuitePage({ run = latestRun }: { run?: BenchmarkRun }) {
  const summary = run.contextRot;
  const mneno = summary?.systems.find((system) => system.name === "mneno");

  return (
    <>
      <PageHeader
        eyebrow="Flagship benchmark"
        title="Mneno Context Rot Suite v1"
        description="A deterministic first-party benchmark for stale suppression, lifecycle behavior, session continuity, context budgets, compaction, and trace-backed decisions."
      />

      {!summary ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">
          Run <code>scripts/run_demo.sh</code> to generate the Context Rot Suite
          result.
        </section>
      ) : (
        <div className="space-y-6">
          <section className="grid gap-4 md:grid-cols-4">
            <SummaryValue
              icon={SearchCheck}
              label="Context Rot Score"
              value={formatScore(mneno?.contextRotScore)}
              detail={mneno?.status === "skipped" ? "Mneno skipped" : "Mneno aggregate"}
            />
            <SummaryValue
              icon={GitCompareArrows}
              label="Systems"
              value={String(summary.systems.length)}
              detail="Same 24 cases"
            />
            <SummaryValue
              icon={Route}
              label="Trace evidence"
              value={run.trace.events + run.trace.decisions > 0 ? "Available" : "Unavailable"}
              detail={run.trace.traceId ?? "See raw trace directory"}
            />
            <SummaryValue
              icon={FileText}
              label="Dataset"
              value={`${summary.caseCount} cases`}
              detail={`${summary.memoryCount} memories`}
            />
          </section>

          <section className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-panel">
            <div className="border-b border-ink-950/10 p-5">
              <p className="font-mono text-xs uppercase text-signal-700">Baseline comparison</p>
              <h2 className="mt-1 text-lg font-semibold">Aggregate scores</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[660px] text-left text-sm">
                <thead className="bg-canvas/70 text-xs uppercase text-ink-600">
                  <tr>
                    <th className="px-5 py-3 font-semibold">System</th>
                    <th className="px-5 py-3 font-semibold">Status</th>
                    <th className="px-5 py-3 text-right font-semibold">Context Rot Score</th>
                    <th className="px-5 py-3 text-right font-semibold">Recall</th>
                    <th className="px-5 py-3 text-right font-semibold">Stale suppression</th>
                    <th className="px-5 py-3 text-right font-semibold">Efficiency</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.systems.map((system) => (
                    <tr key={system.name} className="border-t border-ink-950/10">
                      <td className="px-5 py-4 font-semibold">{systemLabels[system.name] ?? system.name}</td>
                      <td className="px-5 py-4"><StatusBadge status={system.status} /></td>
                      <ScoreCell value={system.contextRotScore} strong />
                      <ScoreCell value={system.metrics.expected_memory_recall} />
                      <ScoreCell value={system.metrics.stale_memory_suppression_rate} />
                      <ScoreCell value={system.metrics.context_efficiency_score} />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-panel">
            <div className="border-b border-ink-950/10 p-5">
              <p className="font-mono text-xs uppercase text-signal-700">Category breakdown</p>
              <h2 className="mt-1 text-lg font-semibold">Eight context-rot failure modes</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-canvas/70 text-xs uppercase text-ink-600">
                  <tr>
                    <th className="px-5 py-3 font-semibold">Category</th>
                    {summary.systems.map((system) => (
                      <th key={system.name} className="px-5 py-3 text-right font-semibold">
                        {systemLabels[system.name] ?? system.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {categoryNames(summary.systems).map((category) => (
                    <tr key={category} className="border-t border-ink-950/10">
                      <td className="px-5 py-4 font-medium">{categoryLabel(category)}</td>
                      {summary.systems.map((system) => (
                        <ScoreCell
                          key={system.name}
                          value={system.categories.find((item) => item.category === category)?.contextRotScore}
                        />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="flex flex-col gap-4 rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-mono text-xs uppercase text-ink-600">Artifacts</p>
              <p className="mt-1 text-sm text-ink-600">
                {summary.failureCount} recorded retrieval failures. Raw traces and exports remain local.
              </p>
            </div>
            {summary.reportUrl ? (
              <a
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-ink-950 px-4 text-sm font-semibold text-white transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-950"
                href={summary.reportUrl}
                download="context_rot_suite_latest.md"
              >
                <FileText aria-hidden="true" size={17} />
                Download report
              </a>
            ) : (
              <code className="text-xs text-ink-600">{summary.reportPath}</code>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function SummaryValue({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof SearchCheck;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-lg border border-ink-950/10 bg-white p-4 shadow-panel">
      <div className="flex items-center gap-2 text-ink-600">
        <Icon aria-hidden="true" size={17} />
        <p className="text-xs font-semibold uppercase">{label}</p>
      </div>
      <p className="mt-3 font-mono text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 truncate text-xs text-ink-600" title={detail}>{detail}</p>
    </div>
  );
}

function ScoreCell({ value, strong = false }: { value: number | null | undefined; strong?: boolean }) {
  return (
    <td className={`px-5 py-4 text-right font-mono tabular-nums ${strong ? "font-semibold" : ""}`}>
      {formatScore(value)}
    </td>
  );
}

function formatScore(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "Skipped";
}

function categoryNames(systems: ContextRotSystemSummary[]): string[] {
  return Array.from(new Set(systems.flatMap((system) => system.categories.map((item) => item.category)))).sort();
}

function categoryLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
