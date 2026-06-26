import { metricDirection, metricLabel } from "./metrics";
import type {
  BenchmarkRun,
  BenchmarkSuite,
  ContextRotCategorySummary,
  ContextRotSummary,
  ContextRotSystemSummary,
  FailureCase,
  FailureCategory,
  FailureReport,
  FailureSeverity,
  LocomoSummary,
  LocomoSystemSummary,
  MnenoCaseDecisionSummary,
  MnenoExecutionSummary,
  MetricResult,
  MnenoBenchmarkExport,
  MnenoTraceExport,
  RetrievalDeepDive,
  RetrievalFailureInspection,
  RetrievalRootCause,
  RootCauseSummary,
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

const mnenoResultModules = import.meta.glob("../../results/mneno/*.json", {
  eager: true,
  import: "default",
}) as Record<string, unknown>;

const locomoResultModules = import.meta.glob("../../results/locomo/dashboard/runs/*.json", {
  eager: true,
  import: "default",
}) as Record<string, unknown>;

const failureReportModules = {
  ...(import.meta.glob("../../results/mneno/failures/*.json", {
    eager: true,
    import: "default",
  }) as Record<string, unknown>),
  ...(import.meta.glob("../../results/locomo/dashboard/failures/*.json", {
    eager: true,
    import: "default",
  }) as Record<string, unknown>),
};

const retrievalDeepDiveModules = import.meta.glob(
  "../../results/locomo/dashboard/deep_dive/*.json",
  {
    eager: true,
    import: "default",
  },
) as Record<string, unknown>;

const reportModules = {
  ...(import.meta.glob("../../results/reports/*.md", {
    eager: true,
    query: "?raw",
    import: "default",
  }) as Record<string, string>),
  ...(import.meta.glob("../../results/locomo/*.md", {
    eager: true,
    query: "?raw",
    import: "default",
  }) as Record<string, string>),
};

const resultModules = {
  ...mnenoResultModules,
  ...locomoResultModules,
};

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
    (typeof raw.dashboard_mneno_status === "string"
      ? raw.dashboard_mneno_status
      : undefined) ??
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
  const locomo = parseLocomoSummary(asObject(metadata?.locomo));
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
    cases:
      typeof raw.dashboard_case_count === "number"
        ? raw.dashboard_case_count
        : results.length,
    source: raw.suite === "locomo" ? "external" : "synthetic",
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
    locomo,
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

export function parseFailureReport(value: unknown): FailureReport {
  const raw = asObject(value);
  const summary = asObject(raw?.summary);
  if (
    !raw ||
    !summary ||
    typeof raw.id !== "string" ||
    typeof raw.benchmark !== "string" ||
    typeof raw.run_id !== "string"
  ) {
    throw new Error("Invalid failure report.");
  }
  const failures = asArray(raw.failures)
    .map(parseFailureCase)
    .filter((failure): failure is FailureCase => failure !== null);
  const globalSummary = parseRootCauseSummary(summary, failures);
  const rawByProvider = asObject(raw.by_provider);
  const providers = Array.from(new Set(failures.map((failure) => failure.provider)));
  const byProvider = Object.fromEntries(
    providers.map((provider) => [
      provider,
      parseRootCauseSummary(
        asObject(rawByProvider?.[provider]),
        failures.filter((failure) => failure.provider === provider),
      ),
    ]),
  );
  return {
    id: raw.id,
    benchmark: raw.benchmark,
    runId: raw.run_id,
    createdAt: typeof raw.created_at === "string" ? raw.created_at : "Unknown",
    failures,
    summary: globalSummary,
    byProvider,
    mnenoOnly: parseRootCauseSummary(
      asObject(raw.mneno_only),
      failures.filter((failure) => failure.provider === "mneno"),
    ),
    baselineOnly: parseRootCauseSummary(
      asObject(raw.baseline_only),
      failures.filter((failure) => isBaselineProvider(failure.provider)),
    ),
    metadata: asObject(raw.metadata) ?? {},
  };
}

export function parseRetrievalDeepDive(value: unknown): RetrievalDeepDive {
  const raw = asObject(value);
  const statistics = asObject(raw?.statistics);
  if (
    !raw ||
    !statistics ||
    typeof raw.benchmark !== "string" ||
    typeof raw.provider !== "string"
  ) {
    throw new Error("Invalid retrieval deep dive.");
  }
  return {
    benchmark: raw.benchmark,
    createdAt: typeof raw.created_at === "string" ? raw.created_at : "Unknown",
    provider: raw.provider,
    totalFailures: numberValue(raw.total_failures),
    sampledFailures: asArray(raw.sampled_failures)
      .map(parseRetrievalInspection)
      .filter((item): item is RetrievalFailureInspection => item !== null),
    rootCauses: countPercentageRecord(raw.root_causes),
    statistics: {
      sampleSize: numberValue(statistics.sample_size),
      expectedEvidenceCount: numberValue(statistics.expected_evidence_count),
      retrievedExpectedCount: numberValue(statistics.retrieved_expected_count),
      candidateExpectedCount: numberValue(statistics.candidate_expected_count),
      retrievalRecall: nullableNumber(statistics.retrieval_recall),
      candidateCoverage: nullableNumber(statistics.candidate_coverage),
      failuresByRootCause: countPercentageRecord(statistics.failures_by_root_cause),
      failuresByConversation: countPercentageRecord(statistics.failures_by_conversation),
      failuresByQuestionType: countPercentageRecord(statistics.failures_by_question_type),
      failuresBySession: countPercentageRecord(statistics.failures_by_session),
      failuresByCategory: countPercentageRecord(statistics.failures_by_category),
    },
    recommendations: asArray(raw.recommendations)
      .map((value) => {
        const item = asObject(value);
        if (!item || typeof item.title !== "string") return null;
        return {
          title: item.title,
          evidence: asArray(item.evidence).map(String),
          expectedImpact:
            typeof item.expected_impact === "string" ? item.expected_impact : "",
          confidence: typeof item.confidence === "string" ? item.confidence : "unknown",
          suggestedCoreArea:
            typeof item.suggested_core_area === "string"
              ? item.suggested_core_area
              : "Unknown",
        };
      })
      .filter((item): item is RetrievalDeepDive["recommendations"][number] => item !== null),
    topFailureCases: asArray(raw.top_failure_cases)
      .map(parseRetrievalInspection)
      .filter((item): item is RetrievalFailureInspection => item !== null),
    recommendedCorePriorities: asArray(raw.recommended_core_priorities).map(String),
    runId: typeof raw.run_id === "string" ? raw.run_id : null,
    deterministicSeed: numberValue(raw.deterministic_seed),
    metadata: asObject(raw.metadata) ?? {},
  };
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

export const failureReports: FailureReport[] = Object.values(failureReportModules)
  .map((value) => {
    try {
      return parseFailureReport(value);
    } catch {
      return null;
    }
  })
  .filter((report): report is FailureReport => report !== null)
  .sort((left, right) => right.createdAt.localeCompare(left.createdAt));

export const latestFailureReport = failureReports[0];

export const retrievalDeepDives: RetrievalDeepDive[] = Object.values(
  retrievalDeepDiveModules,
)
  .map((value) => {
    try {
      return parseRetrievalDeepDive(value);
    } catch {
      return null;
    }
  })
  .filter((report): report is RetrievalDeepDive => report !== null)
  .sort((left, right) => right.createdAt.localeCompare(left.createdAt));

export const latestRetrievalDeepDive = retrievalDeepDives[0];

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
    status: "available",
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

function parseFailureCase(value: unknown): FailureCase | null {
  const raw = asObject(value);
  if (
    !raw ||
    typeof raw.id !== "string" ||
    typeof raw.case_id !== "string" ||
    typeof raw.provider !== "string" ||
    !isFailureCategory(raw.category) ||
    !isFailureSeverity(raw.severity)
  ) {
    return null;
  }
  const provider = raw.provider;
  const category = raw.category;
  const interpretation =
    typeof raw.interpretation === "string"
      ? raw.interpretation
      : providerInterpretation(provider, category);
  const expectedBehavior =
    raw.expected_behavior === true || expectedBaselineBehavior(provider, category);
  const rawAction =
    typeof raw.suggested_action === "string"
      ? raw.suggested_action
      : "Collect more evidence.";
  return {
    id: raw.id,
    benchmark: typeof raw.benchmark === "string" ? raw.benchmark : "unknown",
    caseId: raw.case_id,
    provider,
    category,
    severity: raw.severity,
    query: typeof raw.query === "string" ? raw.query : "",
    expectedIds: asArray(raw.expected_ids).map(String),
    retrievedIds: asArray(raw.retrieved_ids).map(String),
    includedIds: asArray(raw.included_ids).map(String),
    excludedIds: asArray(raw.excluded_ids).map(String),
    forbiddenIds: asArray(raw.forbidden_ids).map(String),
    traceIds: asArray(raw.trace_ids).map(String),
    reason: typeof raw.reason === "string" ? raw.reason : "No reason recorded.",
    evidence: asArray(raw.evidence).map(String),
    suggestedAction: providerAction(provider, rawAction, interpretation),
    expectedBehavior,
    interpretation,
    metadata: asObject(raw.metadata) ?? {},
  };
}

function parseRetrievalInspection(
  value: unknown,
): RetrievalFailureInspection | null {
  const raw = asObject(value);
  if (
    !raw ||
    typeof raw.id !== "string" ||
    typeof raw.case_id !== "string" ||
    typeof raw.provider !== "string" ||
    !isRetrievalRootCause(raw.root_cause)
  ) {
    return null;
  }
  const context = asObject(raw.context_package) ?? {};
  return {
    id: raw.id,
    caseId: raw.case_id,
    provider: raw.provider,
    conversationId:
      typeof raw.conversation_id === "string" ? raw.conversation_id : "unknown",
    questionType:
      typeof raw.question_type === "string" ? raw.question_type : "unknown",
    category: typeof raw.category === "string" ? raw.category : "unknown",
    sessions: asArray(raw.sessions).map(String),
    question: typeof raw.question === "string" ? raw.question : "",
    normalizedQuestion:
      typeof raw.normalized_question === "string" ? raw.normalized_question : "",
    expectedEvidence: asArray(raw.expected_evidence).map((value) => {
      const item = asObject(value) ?? {};
      return {
        evidenceId: String(item.evidence_id ?? "unknown"),
        text: typeof item.text === "string" ? item.text : null,
        sessionId: typeof item.session_id === "string" ? item.session_id : null,
        coreMemoryId:
          typeof item.core_memory_id === "string" ? item.core_memory_id : null,
      };
    }),
    retrievedCandidates: asArray(raw.retrieved_candidates).map((value) => {
      const item = asObject(value) ?? {};
      return {
        id: String(item.id ?? "unknown"),
        coreMemoryId: String(item.core_memory_id ?? "unknown"),
        text: typeof item.text === "string" ? item.text : null,
        score: nullableNumber(item.score),
        rank: nullableNumber(item.rank),
        selected: item.selected === true,
        reasons: asArray(item.reasons).map(String),
      };
    }),
    includedIds: asArray(context.included_memories).map(
      (value) => String(asObject(value)?.id ?? "unknown"),
    ),
    excludedExpectedIds: asArray(context.excluded_memories).map(
      (value) => String(asObject(value)?.id ?? "unknown"),
    ),
    traceIds: asArray(asObject(raw.trace)?.trace_ids).map(String),
    rootCause: raw.root_cause,
    explanation:
      typeof raw.explanation === "string" ? raw.explanation : "No explanation recorded.",
    classificationEvidence: asArray(raw.classification_evidence).map(String),
  };
}

function countPercentageRecord(value: unknown) {
  const raw = asObject(value) ?? {};
  return Object.fromEntries(
    Object.entries(raw).map(([key, item]) => {
      const summary = asObject(item) ?? {};
      return [
        key,
        {
          count: numberValue(summary.count),
          percentage: numberValue(summary.percentage),
        },
      ];
    }),
  );
}

function isRetrievalRootCause(value: unknown): value is RetrievalRootCause {
  return [
    "evidence_not_indexed",
    "candidate_generation_failure",
    "query_normalization_failure",
    "lexical_mismatch",
    "semantic_retrieval_failure",
    "ranking_failure",
    "budget_exclusion",
    "session_bias_failure",
    "lifecycle_filter_failure",
    "unknown",
  ].includes(String(value));
}

function parseRootCauseSummary(
  value: JsonObject | null,
  failures: FailureCase[],
): RootCauseSummary {
  if (!value) {
    return summarizeFailures(failures);
  }
  return {
    totalFailures: numberValue(value.total_failures),
    byCategory: numberRecord(value.by_category),
    byProvider: numberRecord(value.by_provider),
    bySeverity: numberRecord(value.by_severity),
    topSuggestedActions: asArray(value.top_suggested_actions).map(String),
  };
}

function summarizeFailures(failures: FailureCase[]): RootCauseSummary {
  const actionCounts = countStrings(
    failures.map((failure) => failure.suggestedAction),
  );
  return {
    totalFailures: failures.length,
    byCategory: countStrings(failures.map((failure) => failure.category)),
    byProvider: countStrings(failures.map((failure) => failure.provider)),
    bySeverity: countStrings(failures.map((failure) => failure.severity)),
    topSuggestedActions: Object.entries(actionCounts)
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .slice(0, 5)
      .map(([action]) => action),
  };
}

function countStrings(values: string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const value of values) {
    counts[value] = (counts[value] ?? 0) + 1;
  }
  return counts;
}

function isBaselineProvider(provider: string): boolean {
  return provider.endsWith("_baseline");
}

function expectedBaselineBehavior(
  provider: string,
  category: FailureCategory,
): boolean {
  if (provider === "full_context_baseline") {
    return category === "conflict_resolution_failure";
  }
  if (provider === "random_baseline") {
    return category === "retrieval_failure";
  }
  if (provider === "keyword_baseline") {
    return ["retrieval_failure", "session_continuity_failure"].includes(category);
  }
  return false;
}

function providerInterpretation(
  provider: string,
  category: FailureCategory,
): string | null {
  if (provider === "full_context_baseline") {
    return category === "conflict_resolution_failure"
      ? "Full Context intentionally includes all memories, so stale or forbidden-memory use is expected comparison behavior, not by itself a product bug."
      : "Full Context failures quantify the risk and cost of including everything.";
  }
  if (provider === "random_baseline") {
    return "Random retrieval failures are expected baseline behavior and provide a lower-bound comparison.";
  }
  if (provider === "keyword_baseline") {
    return "Keyword retrieval and session failures reflect known lexical and session-awareness limitations of this comparison baseline.";
  }
  if (provider === "mneno") {
    return "This failure is evidence for investigating Mneno Core behavior.";
  }
  return null;
}

function providerAction(
  provider: string,
  action: string,
  interpretation: string | null,
): string {
  if (action.startsWith("Mneno Core:") || action.startsWith("Comparison evidence:")) {
    return action;
  }
  if (provider === "mneno") return `Mneno Core: ${action}`;
  if (isBaselineProvider(provider)) {
    return `Comparison evidence: ${interpretation ?? action}`;
  }
  return action;
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
  const failureAnalysis = asObject(value.failure_analysis);
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
    failureCount:
      typeof failureAnalysis?.failure_count === "number"
        ? failureAnalysis.failure_count
        : asArray(value.failure_cases).length,
  };
}

function parseLocomoSummary(value: JsonObject | null): LocomoSummary | undefined {
  if (!value) {
    return undefined;
  }
  const dataset = asObject(value.dataset) ?? {};
  const scoring = asObject(value.official_scoring) ?? {};
  const validation = asObject(value.dataset_validation) ?? {};
  const rawSystems = asObject(value.systems) ?? {};
  const checkpointing = asObject(value.checkpointing);
  const externalRequests = asObject(value.external_requests);
  const failureAnalysis = asObject(value.failure_analysis);
  const retrievalDeepDive = asObject(value.retrieval_deep_dive);
  const reportPath = typeof value.report_path === "string" ? value.report_path : "";
  const reportSource = Object.entries(reportModules).find(([path]) =>
    path.endsWith("/locomo_latest.md"),
  )?.[1];
  return {
    datasetStatus:
      typeof value.dataset_status === "string" ? value.dataset_status : "unknown",
    datasetPath:
      typeof dataset.source_path === "string"
        ? dataset.source_path
        : typeof dataset.raw_path === "string"
          ? dataset.raw_path
          : "",
    executionStatus: parseStatus(value.execution_status),
    evaluationMode:
      typeof value.evaluation_mode === "string" ? value.evaluation_mode : "retrieval_only",
    conversationCount: numberValue(dataset.conversation_count),
    messageCount: numberValue(dataset.message_count),
    questionCount: numberValue(dataset.question_count),
    categories: numberRecord(dataset.categories),
    systems: Object.entries(rawSystems)
      .map(([name, system]) => parseLocomoSystem(name, asObject(system)))
      .filter((system): system is LocomoSystemSummary => system !== null),
    malformedEvidenceWarningCount: numberValue(
      validation.malformed_evidence_warning_count,
    ),
    reportPath,
    reportUrl: reportSource
      ? `data:text/markdown;charset=utf-8,${encodeURIComponent(reportSource)}`
      : undefined,
    traceDirectory:
      typeof value.trace_directory === "string" ? value.trace_directory : "",
    rawOutputDirectory:
      typeof value.raw_output_directory === "string" ? value.raw_output_directory : "",
    judgePromptDirectory:
      typeof value.judge_prompt_directory === "string" ? value.judge_prompt_directory : "",
    judgeResponseDirectory:
      typeof value.judge_response_directory === "string" ? value.judge_response_directory : "",
    judgeModel: typeof value.judge_model === "string" ? value.judge_model : null,
    judgeProvider: typeof value.judge_provider === "string" ? value.judge_provider : null,
    promptVersion:
      typeof value.prompt_version === "string" ? value.prompt_version : null,
    officialScoringStatus:
      typeof scoring.status === "string" ? scoring.status : "not_implemented",
    officialScoringReason:
      typeof scoring.reason === "string"
        ? scoring.reason
        : "Official LOCOMO scoring is unavailable.",
    checkpointing: checkpointing
      ? {
          enabled: checkpointing.enabled === true,
          resumedCases: numberValue(checkpointing.resumed_cases),
          completedCases: numberValue(checkpointing.completed_cases),
          failedCases: numberValue(checkpointing.failed_cases),
          checkpointDir:
            typeof checkpointing.checkpoint_dir === "string"
              ? checkpointing.checkpoint_dir
              : "",
          fingerprint:
            typeof checkpointing.fingerprint === "string"
              ? checkpointing.fingerprint
              : null,
          evaluationFingerprint:
            typeof checkpointing.evaluation_fingerprint === "string"
              ? checkpointing.evaluation_fingerprint
              : null,
          reuseFailedCheckpoints: checkpointing.reuse_failed_checkpoints === true,
        }
      : undefined,
    externalRequests: externalRequests
      ? {
          enabled: true,
          totalRequests: numberValue(externalRequests.attempts),
          successes: numberValue(externalRequests.successful_requests),
          failures: numberValue(externalRequests.failures),
          retries: numberValue(externalRequests.retries),
          rateLimited: numberValue(externalRequests.rate_limited_429s),
          elapsedSeconds: nullableNumber(externalRequests.elapsed_seconds),
        }
      : undefined,
    failureAnalysis: failureAnalysis
      ? {
          failureCount: numberValue(failureAnalysis.failure_count),
          topCategoriesOverall: countRecord(failureAnalysis.top_categories_overall),
          topCategoriesMneno: countRecord(failureAnalysis.top_categories_mneno),
          topCategoriesBaselines: countRecord(
            failureAnalysis.top_categories_baselines,
          ),
          mnenoSuggestedActions: asArray(
            failureAnalysis.mneno_suggested_actions,
          ).map(String),
          worstCases: asArray(failureAnalysis.worst_cases)
            .map((item) => {
              const raw = asObject(item);
              if (!raw) return null;
              return {
                caseId: String(raw.case_id ?? "unknown"),
                provider: String(raw.provider ?? "unknown"),
                category: String(raw.category ?? "unknown"),
                severity: String(raw.severity ?? "unknown"),
              };
            })
            .filter((item): item is NonNullable<
              LocomoSummary["failureAnalysis"]
            >["worstCases"][number] => item !== null),
          jsonPath:
            typeof failureAnalysis.json_path === "string"
              ? failureAnalysis.json_path
              : null,
          reportPath:
            typeof failureAnalysis.report_path === "string"
              ? failureAnalysis.report_path
              : null,
        }
      : undefined,
    retrievalDeepDive: retrievalDeepDive
      ? {
          sampledFailureCount: numberValue(
            retrievalDeepDive.sampled_failure_count,
          ),
          rootCauses: countRecord(retrievalDeepDive.root_causes),
          jsonPath:
            typeof retrievalDeepDive.json_path === "string"
              ? retrievalDeepDive.json_path
              : null,
          reportPath:
            typeof retrievalDeepDive.report_path === "string"
              ? retrievalDeepDive.report_path
              : null,
        }
      : undefined,
  };
}

function parseLocomoSystem(
  name: string,
  value: JsonObject | null,
): LocomoSystemSummary | null {
  if (!value) {
    return null;
  }
  return {
    name,
    status: parseStatus(value.status),
    metrics: nullableNumberRecord(value.metrics),
    scoreLabels: parseScoreLabels(asObject(value.score_labels)),
    traceIds: asArray(value.trace_ids).map(String),
    judge: parseLocomoJudge(asObject(value.judge)),
    skipReason: typeof value.skip_reason === "string" ? value.skip_reason : null,
    errors: asArray(value.errors).map(String),
  };
}

function parseScoreLabels(value: JsonObject | null): LocomoSystemSummary["scoreLabels"] {
  return {
    officialScore: nullableNumber(value?.official_score),
    diagnosticScore: nullableNumber(value?.diagnostic_score),
    retrievalDiagnostic: nullableNumber(value?.retrieval_diagnostic),
    judgeScore: nullableNumber(value?.judge_score),
  };
}

function parseLocomoJudge(value: JsonObject | null): LocomoSystemSummary["judge"] {
  return {
    status: typeof value?.status === "string" ? value.status : "not_requested",
    model: typeof value?.model === "string" ? value.model : null,
    provider: typeof value?.provider === "string" ? value.provider : null,
    promptVersion:
      typeof value?.prompt_version === "string" ? value.prompt_version : null,
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
  return [
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    "dataset_missing",
  ].includes(String(value))
    ? (value as RunStatus)
    : "failed";
}

function isFailureCategory(value: unknown): value is FailureCategory {
  return [
    "retrieval_failure",
    "ranking_failure",
    "context_budget_failure",
    "lifecycle_filter_failure",
    "session_continuity_failure",
    "conflict_resolution_failure",
    "compaction_failure",
    "answer_generation_failure",
    "judge_failure",
    "dataset_issue",
    "skipped",
    "unknown",
  ].includes(String(value));
}

function isFailureSeverity(value: unknown): value is FailureSeverity {
  return ["low", "medium", "high", "critical"].includes(String(value));
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

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
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

function countRecord(value: unknown): Record<string, number> {
  const object = asObject(value);
  if (!object) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(object)
      .map(([key, raw]) => {
        if (typeof raw === "number") return [key, raw] as const;
        const summary = asObject(raw);
        return typeof summary?.count === "number"
          ? ([key, summary.count] as const)
          : null;
      })
      .filter((entry): entry is readonly [string, number] => entry !== null),
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
