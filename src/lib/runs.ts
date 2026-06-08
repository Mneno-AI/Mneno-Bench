import { metricDirection, metricLabel } from "./metrics";
import type {
  BenchmarkRun,
  BenchmarkSuite,
  ContextRotCategorySummary,
  ContextRotSummary,
  ContextRotSystemSummary,
  MnenoCaseDecisionSummary,
  MnenoExecutionSummary,
  MetricResult,
  MnenoBenchmarkExport,
  MnenoTraceExport,
  RunStatus,
  TraceSummary,
} from "./schema";

export const sampleRun: BenchmarkRun = {
  id: "mneno-suite-demo",
  suite: "Mneno Context Rot Suite",
  startedAt: "Synthetic preview",
  status: "completed",
  systems: ["keyword_baseline", "mneno"],
  cases: 3,
  source: "synthetic",
  mnenoStatus: "skipped",
  metrics: [
    {
      name: "context_efficiency_ratio",
      label: "Context efficiency",
      value: 0.3534,
      description: "Useful evidence tokens divided by supplied context tokens.",
      direction: "higher",
    },
    {
      name: "stale_memory_error_rate",
      label: "Stale memory errors",
      value: 0.1111,
      description: "Retrieved memories explicitly labeled stale for a case.",
      direction: "lower",
    },
    {
      name: "recall_at_3",
      label: "Retrieval recall@3",
      value: 1,
      description: "Expected memories recovered in the first three results.",
      direction: "higher",
    },
    {
      name: "explainability_coverage",
      label: "Explainability",
      value: null,
      description: "Selected memory decisions backed by a trace explanation.",
      direction: "higher",
    },
  ],
  trace: {
    operations: 0,
    events: 0,
    decisions: 0,
    durationMs: null,
    retrieved: 9,
    selected: 3,
    suppressed: 0,
    conflictsResolved: 0,
    explanations: 0,
  },
  benchmarkVersion: "0.1.0",
  mnenoVersion: null,
};

type JsonObject = Record<string, unknown>;

const resultModules = import.meta.glob("../../results/mneno/*.json", {
  eager: true,
  import: "default",
}) as Record<string, unknown>;

const reportModules = import.meta.glob("../../results/reports/*.md", {
  eager: true,
  query: "?raw",
  import: "default",
}) as Record<string, string>;

export function isTraceExport(value: unknown): value is MnenoTraceExport {
  const object = asObject(value);
  return object?.format === "mneno.trace" && object.version === 1;
}

export function isBenchmarkExport(value: unknown): value is MnenoBenchmarkExport {
  const object = asObject(value);
  return object?.format === "mneno.benchmark.result" && object.version === 1;
}

export function parseTraceExport(value: unknown): TraceSummary {
  if (!isTraceExport(value)) {
    throw new Error("Unsupported Mneno trace export.");
  }
  const trace = asObject(value.trace) ?? {};
  return parseTraceSummary(trace);
}

export function parseBenchmarkRun(value: unknown): BenchmarkRun {
  const raw = asObject(value);
  if (!raw || typeof raw.run_id !== "string" || typeof raw.suite !== "string") {
    throw new Error("Invalid Mneno Bench run.");
  }
  const results = asArray(raw.results);
  const mnenoResults = results
    .map((result) => asObject(result))
    .map((result) => asObject(result?.mneno_result))
    .filter((result): result is JsonObject => result !== null);
  const mnenoStatus =
    mnenoResults.find((result) => result.status === "failed")?.status ??
    mnenoResults.find((result) => result.status === "completed")?.status ??
    mnenoResults[0]?.status ??
    "skipped";
  const summaryMetrics = asObject(raw.summary_metrics);
  const mnenoMetrics = asArray(summaryMetrics?.mneno);
  const baselineMetrics = asArray(summaryMetrics?.keyword_baseline);
  const metrics = (mnenoMetrics.length ? mnenoMetrics : baselineMetrics)
    .map(parseMetric)
    .filter((metric): metric is MetricResult => metric !== null);
  const trace = mnenoResults.reduce<TraceSummary>(
    (total, result) => mergeTraces(total, parseTraceSummary(asObject(result.trace_summary))),
    emptyTrace(),
  );
  const metadata = asObject(raw.export_metadata);
  const contextRot = parseContextRotSummary(
    asObject(metadata?.context_rot_suite),
  );
  const mnenoExecution = parseMnenoExecution(
    asObject(metadata?.mneno_execution),
    results,
  );

  return {
    id: raw.run_id,
    suite: raw.suite.replace(/_/g, " "),
    startedAt: typeof raw.started_at === "string" ? raw.started_at : "Unknown",
    status: parseStatus(raw.status),
    systems: asArray(raw.systems).map(String),
    cases: results.length,
    source: "synthetic",
    mnenoStatus: parseStatus(mnenoStatus),
    metrics,
    trace,
    benchmarkVersion:
      typeof raw.benchmark_version === "string" ? raw.benchmark_version : "0.1.0",
    mnenoVersion:
      typeof raw.mneno_version === "string"
        ? raw.mneno_version
        : typeof metadata?.mneno_version === "string"
          ? metadata.mneno_version
          : null,
    contextRot,
    mnenoExecution,
    rawExport: value,
  };
}

export function parseBenchmarkExport(value: unknown): MnenoBenchmarkExport {
  if (!isBenchmarkExport(value)) {
    throw new Error("Unsupported Mneno benchmark export.");
  }
  return value;
}

export const sampleRuns: BenchmarkRun[] = Object.values(resultModules)
  .map((value) => {
    try {
      return parseBenchmarkRun(value);
    } catch {
      return null;
    }
  })
  .filter((run): run is BenchmarkRun => run !== null)
  .sort((left, right) => right.startedAt.localeCompare(left.startedAt));

if (sampleRuns.length === 0) {
  sampleRuns.push(sampleRun);
}

export const latestRun = sampleRuns[0];

export const suites: BenchmarkSuite[] = [
  {
    id: "mneno-suite",
    name: "Mneno Context Rot Suite",
    role: "Primary product validation",
    status: "available",
    difficulty: "first-party",
  },
  {
    id: "locomo",
    name: "LOCOMO",
    role: "External validation layer",
    status: "planned",
    difficulty: "easy",
  },
  {
    id: "longmemeval",
    name: "LongMemEval",
    role: "Long-term memory validation",
    status: "planned",
    difficulty: "medium",
  },
  {
    id: "beam",
    name: "BEAM",
    role: "External stress test",
    status: "planned",
    difficulty: "hard",
  },
];

function parseMetric(value: unknown): MetricResult | null {
  const metric = asObject(value);
  if (!metric || typeof metric.name !== "string") {
    return null;
  }
  return {
    name: metric.name,
    label: metricLabel(metric.name),
    value: typeof metric.value === "number" ? metric.value : null,
    description: typeof metric.description === "string" ? metric.description : "",
    direction: metricDirection(metric.name),
  };
}

function parseContextRotSummary(value: JsonObject | null): ContextRotSummary | undefined {
  if (!value) {
    return undefined;
  }
  const dataset = asObject(value.dataset);
  const rawSystems = asObject(value.systems);
  if (!dataset || !rawSystems) {
    return undefined;
  }
  const systems = Object.entries(rawSystems)
    .map(([name, system]) => parseContextRotSystem(name, asObject(system)))
    .filter((system): system is ContextRotSystemSummary => system !== null);
  const reportPath = typeof value.report_path === "string" ? value.report_path : "";
  const reportSource = Object.entries(reportModules).find(([path]) =>
    path.endsWith("/context_rot_suite_latest.md"),
  )?.[1];
  return {
    memoryCount: numberValue(dataset.memory_count),
    caseCount: numberValue(dataset.case_count),
    systems,
    reportPath,
    reportUrl: reportSource
      ? `data:text/markdown;charset=utf-8,${encodeURIComponent(reportSource)}`
      : undefined,
    traceDirectory:
      typeof value.trace_directory === "string" ? value.trace_directory : "",
    exportDirectory:
      typeof value.export_directory === "string" ? value.export_directory : "",
    failureCount: asArray(value.failure_cases).length,
  };
}

function parseContextRotSystem(
  name: string,
  value: JsonObject | null,
): ContextRotSystemSummary | null {
  if (!value) {
    return null;
  }
  const rawCategories = asObject(value.categories) ?? {};
  const categories = Object.entries(rawCategories)
    .map(([category, summary]) =>
      parseContextRotCategory(category, asObject(summary)),
    )
    .filter((category): category is ContextRotCategorySummary => category !== null);
  return {
    name,
    status: parseStatus(value.status),
    contextRotScore:
      typeof value.context_rot_score === "number" ? value.context_rot_score : null,
    metrics: nullableNumberRecord(value.metrics),
    categories,
  };
}

function parseContextRotCategory(
  category: string,
  value: JsonObject | null,
): ContextRotCategorySummary | null {
  if (!value) {
    return null;
  }
  return {
    category,
    caseCount: numberValue(value.case_count),
    contextRotScore:
      typeof value.context_rot_score === "number" ? value.context_rot_score : null,
    metrics: nullableNumberRecord(value.metrics),
  };
}

function parseMnenoExecution(
  value: JsonObject | null,
  results: unknown[],
): MnenoExecutionSummary | undefined {
  if (!value) {
    return undefined;
  }
  const capability = asObject(value.capability_report) ?? {};
  return {
    memoriesLoaded: numberValue(value.memories_loaded),
    sessionsCreated: numberValue(value.sessions_created),
    conflictsDetected: numberValue(value.conflicts_detected),
    hierarchyEvaluated: value.hierarchy_evaluated === true,
    hierarchyTransitions: numberRecord(value.hierarchy_transitions),
    compactionPreviewed: value.compaction_previewed === true,
    compactionStats: numberRecord(value.compaction_stats),
    tracesExported: numberValue(value.traces_exported),
    capabilityErrors: stringRecord(value.capability_errors),
    capabilityReport: {
      available: capability.available === true,
      version: typeof capability.version === "string" ? capability.version : null,
      capabilities: booleanRecord(capability.capabilities),
      missing: asArray(capability.missing).map(String),
      partial: capability.partial === true,
    },
    decisions: results
      .map(parseDecisionSummary)
      .filter((decision): decision is MnenoCaseDecisionSummary => decision !== null),
  };
}

function parseDecisionSummary(value: unknown): MnenoCaseDecisionSummary | null {
  const result = asObject(value);
  const benchmarkCase = asObject(result?.case);
  const mneno = asObject(result?.mneno_result);
  const decision = asObject(mneno?.decision_summary);
  if (!benchmarkCase || !decision || typeof benchmarkCase.id !== "string") {
    return null;
  }
  const inclusion = asObject(decision.inclusion_reasons) ?? {};
  const exclusion = asObject(decision.exclusion_reasons) ?? {};
  let reasonCount = 0;
  for (const reasons of [...Object.values(inclusion), ...Object.values(exclusion)]) {
    reasonCount += asArray(reasons).length;
  }
  const metadata = asObject(benchmarkCase.metadata);
  return {
    caseId: benchmarkCase.id,
    category: typeof metadata?.category === "string" ? metadata.category : "unknown",
    includedIds: asArray(decision.included_ids).map(String),
    excludedIds: asArray(decision.excluded_ids).map(String),
    traceIds: asArray(decision.trace_ids).map(String),
    reasonCount,
  };
}

function parseTraceSummary(value: JsonObject | null): TraceSummary {
  if (!value) {
    return emptyTrace();
  }
  return {
    traceId:
      typeof value.trace_id === "string"
        ? value.trace_id
        : typeof value.id === "string"
          ? value.id
          : undefined,
    operations: count(value.operation_count, value.operations),
    events: count(value.event_count, value.events),
    decisions: count(value.decision_count, value.decisions),
    durationMs:
      typeof value.duration_ms === "number"
        ? value.duration_ms
        : typeof value.duration === "number"
          ? value.duration
          : null,
    retrieved: count(undefined, value.retrieved_memory_ids),
    selected: count(undefined, value.selected_memory_ids),
    suppressed: count(undefined, value.suppressed_memory_ids),
    conflictsResolved: count(undefined, value.conflict_resolutions),
    explanations: count(undefined, value.explanations),
  };
}

function mergeTraces(left: TraceSummary, right: TraceSummary): TraceSummary {
  return {
    traceId: left.traceId ?? right.traceId,
    operations: left.operations + right.operations,
    events: left.events + right.events,
    decisions: left.decisions + right.decisions,
    durationMs:
      left.durationMs === null && right.durationMs === null
        ? null
        : (left.durationMs ?? 0) + (right.durationMs ?? 0),
    retrieved: left.retrieved + right.retrieved,
    selected: left.selected + right.selected,
    suppressed: left.suppressed + right.suppressed,
    conflictsResolved: left.conflictsResolved + right.conflictsResolved,
    explanations: left.explanations + right.explanations,
  };
}

function emptyTrace(): TraceSummary {
  return {
    operations: 0,
    events: 0,
    decisions: 0,
    durationMs: null,
    retrieved: 0,
    selected: 0,
    suppressed: 0,
    conflictsResolved: 0,
    explanations: 0,
  };
}

function count(explicit: unknown, collection: unknown): number {
  if (typeof explicit === "number") {
    return explicit;
  }
  return Array.isArray(collection) ? collection.length : 0;
}

function parseStatus(value: unknown): RunStatus {
  return ["pending", "running", "completed", "failed", "skipped"].includes(
    String(value),
  )
    ? (value as RunStatus)
    : "failed";
}

function asObject(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numberValue(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

function numberRecord(value: unknown): Record<string, number> {
  const object = asObject(value);
  if (!object) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(object).filter(
      (entry): entry is [string, number] => typeof entry[1] === "number",
    ),
  );
}

function nullableNumberRecord(value: unknown): Record<string, number | null> {
  const object = asObject(value);
  if (!object) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(object).filter(
      (entry): entry is [string, number | null] =>
        typeof entry[1] === "number" || entry[1] === null,
    ),
  );
}

function booleanRecord(value: unknown): Record<string, boolean> {
  const object = asObject(value);
  if (!object) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(object).filter(
      (entry): entry is [string, boolean] => typeof entry[1] === "boolean",
    ),
  );
}

function stringRecord(value: unknown): Record<string, string> {
  const object = asObject(value);
  if (!object) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(object).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}
