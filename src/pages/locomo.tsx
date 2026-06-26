import {
  Activity,
  AlertTriangle,
  ArchiveRestore,
  Database,
  FileText,
  Landmark,
  Network,
  Route,
  SearchCheck,
  TriangleAlert,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { StatusBadge } from "../components/runs-table";
import type { PageKey } from "../components/sidebar";
import { sampleRuns } from "../lib/runs";
import type { BenchmarkRun, LocomoSystemSummary } from "../lib/schema";
import { PageHeader } from "./dashboard";

const labels: Record<string, string> = {
  keyword_baseline: "Keyword",
  full_context_baseline: "Full Context",
  random_baseline: "Random",
  mneno: "Mneno",
};

export function LocomoPage({
  run = latestLocomoRun(),
  onNavigate,
}: {
  run?: BenchmarkRun;
  onNavigate?: (page: PageKey) => void;
}) {
  const summary = run?.locomo;

  return (
    <>
      <PageHeader
        eyebrow="External validation"
        title="LOCOMO"
        description="The first external benchmark pipeline for Mneno Bench. Dataset loading, validation, baselines, Mneno execution, normalization, checkpointing, failure analysis, and local reports are tracked without optimizing for benchmark scores."
      />

      {!summary || !run ? (
        <NoRunState />
      ) : (
        <LocomoSummaryView run={run} onNavigate={onNavigate} />
      )}
    </>
  );
}

function LocomoSummaryView({
  run,
  onNavigate,
}: {
  run: BenchmarkRun;
  onNavigate?: (page: PageKey) => void;
}) {
  const summary = run.locomo;
  if (!summary) return null;

  const datasetMissing =
    summary.datasetStatus === "missing" ||
    summary.datasetStatus === "dataset_missing" ||
    run.status === "dataset_missing";
  const mneno = summary.systems.find((system) => system.name === "mneno");

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-4">
        <SummaryValue
          icon={Database}
          label="Dataset"
          value={datasetMissing ? "Dataset missing" : "Available"}
          detail={`${summary.conversationCount} conversations`}
        />
        <SummaryValue
          icon={Landmark}
          label="Mode"
          value={formatLabel(summary.evaluationMode)}
          detail={`${summary.questionCount} questions`}
        />
        <SummaryValue
          icon={SearchCheck}
          label="Mneno"
          value={formatLabel(mneno?.status ?? "skipped")}
          detail={run.mnenoVersion ?? "Optional dependency"}
        />
        <SummaryValue
          icon={TriangleAlert}
          label="Failures"
          value={String(summary.failureAnalysis?.failureCount ?? 0)}
          detail="Evidence-backed cases"
        />
      </section>

      {datasetMissing ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 leading-6 text-amber-950">
          <h2 className="font-semibold">LOCOMO dataset is not installed</h2>
          <p className="mt-2 text-sm">
            The runner records this as a skipped benchmark state. Add the local
            processed dataset when you want external evaluation results.
          </p>
          <p className="mt-2 font-mono text-xs">{summary.datasetStatus}</p>
          <PathLine
            label="Expected source"
            value={summary.datasetPath || "data/locomo/raw/locomo10.json"}
          />
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-2">
        <CheckpointCard run={run} />
        <ExternalRequestsCard run={run} />
        <FailureAnalysisCard run={run} onNavigate={onNavigate} />
        <DeepDiveCard run={run} onNavigate={onNavigate} />
      </section>

      <section className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-panel">
        <div className="border-b border-ink-950/10 p-5">
          <p className="font-mono text-xs uppercase text-signal-700">Execution</p>
          <h2 className="mt-1 text-lg font-semibold">Latest LOCOMO run</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[980px] text-left text-sm">
            <thead className="bg-canvas/70 text-xs uppercase text-ink-600">
              <tr>
                <th className="px-5 py-3 font-medium">System</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Diagnostic</th>
                <th className="px-5 py-3 font-medium">Evidence Recall</th>
                <th className="px-5 py-3 font-medium">Judge</th>
                <th className="px-5 py-3 font-medium">Retrieved</th>
                <th className="px-5 py-3 font-medium">Traces</th>
                <th className="px-5 py-3 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-950/10">
              {summary.systems.map((system) => (
                <SystemRow key={system.name} system={system} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
          <p className="font-mono text-xs uppercase text-signal-700">Dataset</p>
          <h2 className="mt-1 text-lg font-semibold">Question Categories</h2>
          <dl className="mt-4 space-y-3">
            {Object.entries(summary.categories).map(([category, count]) => (
              <div
                className="flex items-center justify-between gap-4 rounded-md bg-canvas p-3"
                key={category}
              >
                <dt className="text-sm text-ink-600">{formatLabel(category)}</dt>
                <dd className="font-mono text-sm font-semibold tabular-nums">
                  {count}
                </dd>
              </div>
            ))}
          </dl>
          {summary.malformedEvidenceWarningCount > 0 ? (
            <p className="mt-4 text-sm leading-6 text-amber-700">
              {summary.malformedEvidenceWarningCount} malformed evidence
              annotations were preserved as warnings.
            </p>
          ) : null}
        </section>

        <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
          <p className="font-mono text-xs uppercase text-signal-700">Scoring</p>
          <h2 className="mt-1 text-lg font-semibold">
            {formatLabel(summary.officialScoringStatus)}
          </h2>
          <p className="mt-3 text-sm leading-6 text-ink-600">
            {summary.officialScoringReason} Retrieval diagnostics,
            deterministic answer scoring, and optional judge outputs remain
            separately labeled.
          </p>
        </section>

        <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
          <p className="font-mono text-xs uppercase text-signal-700">llm judge</p>
          <h2 className="mt-1 text-lg font-semibold">
            {formatLabel(summary.systems[0]?.judge.status ?? "not_requested")}
          </h2>
          <p className="mt-3 text-sm leading-6 text-ink-600">
            Provider: {summary.judgeProvider ?? "none"} · Model:{" "}
            {summary.judgeModel ?? "none"} · Prompt:{" "}
            {summary.promptVersion ?? "none"}
          </p>
        </section>
      </section>

      <section className="flex flex-col gap-4 rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-mono text-xs uppercase text-signal-700">Artifacts</p>
          <h2 className="mt-1 text-lg font-semibold">Local Reports and Traces</h2>
          <p className="mt-2 text-sm leading-6 text-ink-600">
            Result JSON, Markdown report, raw outputs, traces, judge prompts,
            judge responses, failure analysis, and checkpoint artifacts remain
            local.
          </p>
          <div className="mt-3 space-y-1">
            <PathLine label="Raw outputs" value={summary.rawOutputDirectory} />
            <PathLine label="Traces" value={summary.traceDirectory} />
            <PathLine label="Judge prompts" value={summary.judgePromptDirectory} />
            <PathLine
              label="Judge responses"
              value={summary.judgeResponseDirectory}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {onNavigate ? (
            <button
              type="button"
              onClick={() => onNavigate("failures")}
              className="min-h-11 cursor-pointer rounded-md border border-ink-950/10 px-4 text-sm font-semibold text-ink-800 transition-colors hover:bg-canvas"
            >
              View failures
            </button>
          ) : null}
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
        </div>
      </section>
    </div>
  );
}

function CheckpointCard({ run }: { run: BenchmarkRun }) {
  const checkpointing = run.locomo?.checkpointing;
  return (
    <InsightCard
      icon={ArchiveRestore}
      eyebrow="Checkpointing"
      title={checkpointing?.enabled ? "Resume-aware execution" : "Not recorded"}
    >
      {checkpointing ? (
        <>
          <MetricList
            values={[
              ["Resumed cases", checkpointing.resumedCases],
              ["Completed checkpoints", checkpointing.completedCases],
              ["Failed checkpoints", checkpointing.failedCases],
              ["Reuse failed", checkpointing.reuseFailedCheckpoints ? "yes" : "no"],
            ]}
          />
          <PathLine label="Directory" value={checkpointing.checkpointDir} />
          <PathLine label="Fingerprint" value={checkpointing.fingerprint} />
        </>
      ) : (
        <p className="text-sm leading-6 text-ink-600">
          This run does not include checkpoint metadata.
        </p>
      )}
    </InsightCard>
  );
}

function ExternalRequestsCard({ run }: { run: BenchmarkRun }) {
  const requests = run.locomo?.externalRequests;
  return (
    <InsightCard
      icon={Network}
      eyebrow="External calls"
      title={requests ? `${requests.totalRequests} attempts` : "Not recorded"}
    >
      {requests ? (
        <MetricList
          values={[
            ["Successful", requests.successes],
            ["Failures", requests.failures],
            ["Retries", requests.retries],
            ["429 rate limits", requests.rateLimited],
          ]}
        />
      ) : (
        <p className="text-sm leading-6 text-ink-600">
          This run does not include external request statistics.
        </p>
      )}
    </InsightCard>
  );
}

function FailureAnalysisCard({
  run,
  onNavigate,
}: {
  run: BenchmarkRun;
  onNavigate?: (page: PageKey) => void;
}) {
  const analysis = run.locomo?.failureAnalysis;
  return (
    <InsightCard
      icon={AlertTriangle}
      eyebrow="Failure analysis"
      title={analysis ? `${analysis.failureCount} observed failures` : "Not recorded"}
      action={
        analysis && onNavigate ? (
          <button
            type="button"
            onClick={() => onNavigate("failures")}
            className="text-sm font-semibold text-signal-700 hover:underline"
          >
            Open failures
          </button>
        ) : undefined
      }
    >
      {analysis ? (
        <>
          <CountPills values={analysis.topCategoriesOverall} />
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <MiniBreakdown title="Mneno" values={analysis.topCategoriesMneno} />
            <MiniBreakdown
              title="Baselines"
              values={analysis.topCategoriesBaselines}
            />
          </div>
          {analysis.mnenoSuggestedActions.length ? (
            <ul className="mt-4 space-y-2 text-sm leading-6 text-ink-600">
              {analysis.mnenoSuggestedActions.slice(0, 2).map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ul>
          ) : null}
        </>
      ) : (
        <p className="text-sm leading-6 text-ink-600">
          Run failure analysis to summarize root causes and worst cases.
        </p>
      )}
    </InsightCard>
  );
}

function DeepDiveCard({
  run,
  onNavigate,
}: {
  run: BenchmarkRun;
  onNavigate?: (page: PageKey) => void;
}) {
  const deepDive = run.locomo?.retrievalDeepDive;
  return (
    <InsightCard
      icon={Activity}
      eyebrow="Retrieval deep dive"
      title={
        deepDive
          ? `${deepDive.sampledFailureCount} sampled failures`
          : "Not recorded"
      }
      action={
        deepDive && onNavigate ? (
          <button
            type="button"
            onClick={() => onNavigate("deep-dive")}
            className="text-sm font-semibold text-signal-700 hover:underline"
          >
            Open deep dive
          </button>
        ) : undefined
      }
    >
      {deepDive ? (
        <CountPills values={deepDive.rootCauses} />
      ) : (
        <p className="text-sm leading-6 text-ink-600">
          Run retrieval deep dive to inspect candidate coverage, ranking,
          session bias, and unknowns.
        </p>
      )}
    </InsightCard>
  );
}

function SystemRow({ system }: { system: LocomoSystemSummary }) {
  return (
    <tr>
      <td className="px-5 py-4 font-semibold">
        {labels[system.name] ?? formatLabel(system.name)}
      </td>
      <td className="px-5 py-4">
        <StatusBadge status={system.status} />
      </td>
      <ScoreCell value={system.scoreLabels.diagnosticScore} />
      <ScoreCell
        value={system.scoreLabels.retrievalDiagnostic ?? system.metrics.evidence_recall}
      />
      <ScoreCell value={system.scoreLabels.judgeScore} />
      <ScoreCell value={system.metrics.retrieved_dialog_count} count />
      <td className="px-5 py-4 font-mono text-sm tabular-nums">
        {system.traceIds.length}
      </td>
      <td className="max-w-xs px-5 py-4 text-ink-600">
        {system.skipReason ??
          (system.errors.length
            ? system.errors.join("; ")
            : formatLabel(system.judge.status))}
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
    <section className="rounded-lg border border-ink-950/10 bg-white p-4 shadow-panel">
      <div className="flex items-center gap-3 text-ink-600">
        <Icon aria-hidden="true" size={18} />
        <p className="text-xs uppercase">{label}</p>
      </div>
      <p className="mt-3 text-2xl font-semibold capitalize">{value}</p>
      <p className="mt-1 text-sm text-ink-600">{detail}</p>
    </section>
  );
}

function InsightCard({
  icon: Icon,
  eyebrow,
  title,
  action,
  children,
}: {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 gap-3">
          <span className="mt-1 flex size-9 shrink-0 items-center justify-center rounded-md bg-canvas text-signal-700">
            <Icon aria-hidden="true" size={18} />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-xs uppercase text-signal-700">{eyebrow}</p>
            <h2 className="mt-1 text-lg font-semibold">{title}</h2>
          </div>
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function MetricList({
  values,
}: {
  values: Array<[string, string | number]>;
}) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2">
      {values.map(([label, value]) => (
        <div key={label} className="rounded-md bg-canvas p-3">
          <dt className="text-xs uppercase text-ink-600">{label}</dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function CountPills({ values }: { values: Record<string, number> }) {
  const entries = Object.entries(values)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, 5);
  if (!entries.length) {
    return <p className="text-sm text-ink-600">No counts recorded.</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([label, count]) => (
        <span
          key={label}
          className="rounded-md border border-ink-950/10 bg-canvas px-2.5 py-1.5 text-xs font-semibold text-ink-700"
        >
          {formatLabel(label)} · {count}
        </span>
      ))}
    </div>
  );
}

function MiniBreakdown({
  title,
  values,
}: {
  title: string;
  values: Record<string, number>;
}) {
  return (
    <div className="rounded-md border border-ink-950/10 p-3">
      <p className="text-xs font-semibold uppercase text-ink-600">{title}</p>
      <div className="mt-3">
        <CountPills values={values} />
      </div>
    </div>
  );
}

function PathLine({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  if (!value) return null;
  return (
    <p className="mt-3 min-w-0 text-xs leading-5 text-ink-600">
      <span className="font-semibold text-ink-800">{label}: </span>
      <code className="break-all font-mono">{value}</code>
    </p>
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
    <td className="px-5 py-4 font-mono text-sm tabular-nums">
      {typeof value === "number" ? (count ? value : formatScore(value)) : "n/a"}
    </td>
  );
}

function NoRunState() {
  return (
    <section className="rounded-lg border border-ink-950/10 bg-white p-8 shadow-panel">
      <div className="flex items-start gap-3">
        <Route aria-hidden="true" className="mt-1 text-signal-700" size={22} />
        <div>
          <h2 className="text-lg font-semibold">No LOCOMO run found</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-600">
            Run the LOCOMO benchmark to generate local dashboard JSON artifacts.
            Missing datasets are recorded as skipped results rather than
            crashing the dashboard.
          </p>
        </div>
      </div>
    </section>
  );
}

function latestLocomoRun(): BenchmarkRun | undefined {
  return sampleRuns.find((run) => run.suite.toLowerCase() === "locomo");
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatScore(value: number): string {
  if (value >= 0 && value <= 1) {
    return `${Math.round(value * 100)}%`;
  }
  return value.toFixed(3);
}
