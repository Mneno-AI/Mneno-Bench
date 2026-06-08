import { Database, FileText, Landmark, Route, SearchCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { StatusBadge } from "../components/runs-table";
import { sampleRuns } from "../lib/runs";
import type { BenchmarkRun, LocomoSystemSummary } from "../lib/schema";
import { PageHeader } from "./dashboard";

const labels: Record<string, string> = {
  keyword_baseline: "Keyword baseline",
  full_context_baseline: "Full-context baseline",
  mneno: "Mneno",
};

export function LocomoPage({ run = latestLocomoRun() }: { run?: BenchmarkRun }) {
  const summary = run?.locomo;

  return (
    <>
      <PageHeader
        eyebrow="External validation"
        title="LOCOMO"
        description="The first external benchmark pipeline for Mneno Bench. Dataset loading, validation, baselines, Mneno execution, normalization, and local reports are tracked without optimizing for benchmark scores."
      />

      {!summary ? <NoRunState /> : <LocomoSummaryView run={run} />}
    </>
  );
}

function LocomoSummaryView({ run }: { run: BenchmarkRun }) {
  const summary = run.locomo;
  if (!summary) {
    return null;
  }
  const mneno = summary.systems.find((system) => system.name === "mneno");
  const datasetMissing = summary.datasetStatus === "dataset_missing";

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-4">
        <SummaryValue
          icon={Database}
          label="Dataset"
          value={datasetMissing ? "Missing" : "Available"}
          detail={`${summary.conversationCount} conversations`}
        />
        <SummaryValue
          icon={Landmark}
          label="Mode"
          value={summary.evaluationMode.replace(/_/g, " ")}
          detail={`${summary.questionCount} questions`}
        />
        <SummaryValue
          icon={SearchCheck}
          label="Mneno"
          value={mneno?.status.replace(/_/g, " ") ?? "skipped"}
          detail={run.mnenoVersion ?? "Optional dependency"}
        />
        <SummaryValue
          icon={Route}
          label="Trace IDs"
          value={String(summary.systems.reduce((total, system) => total + system.traceIds.length, 0))}
          detail={summary.traceDirectory || "No traces exported"}
        />
      </section>

      {datasetMissing ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
          <h2 className="text-base font-semibold">Dataset missing</h2>
          <p className="mt-2">
            Place the official LOCOMO file at <code>data/locomo/raw/locomo10.json</code>,
            then run <code>python -m benchmarks.locomo.run</code>. The repository
            intentionally works without the dataset and records this state instead
            of crashing.
          </p>
          <p className="mt-2 font-mono text-xs">Status: {summary.datasetStatus}</p>
        </section>
      ) : null}

      <section className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-panel">
        <div className="border-b border-ink-950/10 p-5">
          <p className="font-mono text-xs uppercase text-signal-700">Execution</p>
          <h2 className="mt-1 text-lg font-semibold">Latest LOCOMO run</h2>
          <p className="mt-2 text-sm text-ink-600">
            Evidence recall is a retrieval diagnostic over official evidence dialog
            IDs. Answer diagnostics and judge scores are kept in separate labels.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="bg-canvas/70 text-xs uppercase text-ink-600">
              <tr>
                <th className="px-5 py-3 font-semibold">System</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 text-right font-semibold">Official</th>
                <th className="px-5 py-3 text-right font-semibold">Diagnostic</th>
                <th className="px-5 py-3 text-right font-semibold">Evidence Recall</th>
                <th className="px-5 py-3 text-right font-semibold">Judge</th>
                <th className="px-5 py-3 text-right font-semibold">Retrieved Dialogs</th>
                <th className="px-5 py-3 text-right font-semibold">Traces</th>
                <th className="px-5 py-3 font-semibold">Status detail</th>
              </tr>
            </thead>
            <tbody>
              {summary.systems.map((system) => (
                <SystemRow key={system.name} system={system} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
          <p className="font-mono text-xs uppercase text-signal-700">Categories</p>
          <h2 className="mt-1 text-lg font-semibold">Question mix</h2>
          <dl className="mt-4 grid gap-3 sm:grid-cols-2">
            {Object.entries(summary.categories).map(([category, count]) => (
              <div key={category} className="rounded-md bg-canvas p-3">
                <dt className="text-xs uppercase text-ink-600">{formatLabel(category)}</dt>
                <dd className="mt-1 font-mono text-lg font-semibold">{count}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
          <p className="font-mono text-xs uppercase text-signal-700">Official scoring</p>
          <h2 className="mt-1 text-lg font-semibold">{formatLabel(summary.officialScoringStatus)}</h2>
          <p className="mt-3 text-sm leading-6 text-ink-600">
            {summary.officialScoringReason} Retrieval diagnostics, deterministic
            answer diagnostics, and judge scores are reported separately.
          </p>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
          <p className="font-mono text-xs uppercase text-signal-700">Judge</p>
          <h2 className="mt-1 text-lg font-semibold">{formatLabel(summary.systems[0]?.judge.status ?? "not_requested")}</h2>
          <p className="mt-3 text-sm leading-6 text-ink-600">
            Model: {summary.judgeModel ?? "not configured"}. Provider: {summary.judgeProvider ?? "not configured"}.
            Prompt version: {summary.promptVersion ?? "unavailable"}.
          </p>
        </div>
        <div className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
          <p className="font-mono text-xs uppercase text-signal-700">Dataset validation</p>
          <h2 className="mt-1 text-lg font-semibold">{summary.malformedEvidenceWarningCount} malformed evidence warnings</h2>
          <p className="mt-3 text-sm leading-6 text-ink-600">
            Strict validation remains the default. Non-strict runs surface malformed
            evidence warnings instead of mutating LOCOMO annotations.
          </p>
        </div>
      </section>

      <section className="flex flex-col gap-4 rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-mono text-xs uppercase text-ink-600">Artifacts</p>
          <p className="mt-1 text-sm text-ink-600">
            Result JSON, Markdown report, raw outputs, traces, judge prompts, and judge responses remain local.
          </p>
        </div>
        {summary.reportUrl ? (
          <a
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-ink-950 px-4 text-sm font-semibold text-white transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-950"
            href={summary.reportUrl}
            download="locomo_latest.md"
          >
            <FileText aria-hidden="true" size={17} />
            Download report
          </a>
        ) : (
          <code className="text-xs text-ink-600">{summary.reportPath}</code>
        )}
      </section>
    </div>
  );
}

function NoRunState() {
  return (
    <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
      <h2 className="text-base font-semibold">No LOCOMO run found</h2>
      <p className="mt-2">
        Run <code>python -m benchmarks.locomo.run</code>. If the dataset is absent,
        the runner will still write a <code>dataset_missing</code> result for the
        dashboard.
      </p>
    </section>
  );
}

function SystemRow({ system }: { system: LocomoSystemSummary }) {
  return (
    <tr className="border-t border-ink-950/10">
      <td className="px-5 py-4 font-semibold">{labels[system.name] ?? system.name}</td>
      <td className="px-5 py-4">
        <StatusBadge status={system.status} />
      </td>
      <ScoreCell value={system.scoreLabels.officialScore} />
      <ScoreCell value={system.scoreLabels.diagnosticScore} />
      <ScoreCell value={system.scoreLabels.retrievalDiagnostic ?? system.metrics.evidence_recall} />
      <ScoreCell value={system.scoreLabels.judgeScore} />
      <ScoreCell value={system.metrics.retrieved_dialog_count} count />
      <td className="px-5 py-4 text-right font-mono tabular-nums">
        {system.traceIds.length}
      </td>
      <td className="max-w-xs px-5 py-4 text-ink-600">
        {system.skipReason ?? (system.errors.length ? system.errors.join("; ") : formatLabel(system.judge.status))}
      </td>
    </tr>
  );
}

function SummaryValue({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: LucideIcon;
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
      <p className="mt-3 truncate font-mono text-2xl font-semibold tabular-nums capitalize">
        {value}
      </p>
      <p className="mt-1 truncate text-xs text-ink-600" title={detail}>{detail}</p>
    </div>
  );
}

function ScoreCell({
  value,
  count = false,
}: {
  value: number | null | undefined;
  count?: boolean;
}) {
  return (
    <td className="px-5 py-4 text-right font-mono tabular-nums">
      {typeof value === "number" ? (count ? value : `${Math.round(value * 100)}%`) : "Unavailable"}
    </td>
  );
}

function latestLocomoRun(): BenchmarkRun | undefined {
  return sampleRuns.find((run) => run.locomo !== undefined);
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
