import { describe, expect, it } from "vitest";

import {
  parseBenchmarkExport,
  parseBenchmarkRun,
  parseFailureReport,
  parseRetrievalDeepDive,
  parseTraceExport,
} from "./runs";

describe("dashboard result parsing", () => {
  it("loads a durable benchmark run with versions and normalized trace data", () => {
    const run = parseBenchmarkRun({
      schema_version: "1.0",
      benchmark_version: "0.2.0",
      mneno_version: "0.3.2",
      run_id: "run-1",
      suite: "mneno_context_rot_suite",
      status: "completed",
      started_at: "2026-06-07T12:00:00Z",
      systems: ["keyword_baseline", "mneno"],
      summary_metrics: {
        mneno: [
          {
            name: "precision_at_3",
            value: 1,
            description: "Precision",
          },
        ],
      },
      results: [
        {
          mneno_result: {
            status: "completed",
            trace_summary: {
              trace_id: "trace-1",
              operation_count: 2,
              event_count: 3,
              decision_count: 1,
              duration_ms: 5,
              retrieved_memory_ids: ["a"],
            },
          },
        },
      ],
    });

    expect(run.id).toBe("run-1");
    expect(run.benchmarkVersion).toBe("0.2.0");
    expect(run.mnenoVersion).toBe("0.3.2");
    expect(run.metrics[0]?.value).toBe(1);
    expect(run.trace).toMatchObject({
      traceId: "trace-1",
      operations: 2,
      events: 3,
      decisions: 1,
      durationMs: 5,
      retrieved: 1,
    });
  });

  it("validates Mneno benchmark and trace exports", () => {
    const benchmark = parseBenchmarkExport({
      format: "mneno.benchmark.result",
      version: 1,
      run_id: "core-run",
    });
    const trace = parseTraceExport({
      format: "mneno.trace",
      version: 1,
      trace: {
        id: "trace-2",
        operations: [{}],
        events: [{}, {}],
        decisions: [{}],
        duration_ms: 4,
      },
    });

    expect(benchmark.run_id).toBe("core-run");
    expect(trace).toMatchObject({
      traceId: "trace-2",
      operations: 1,
      events: 2,
      decisions: 1,
      durationMs: 4,
    });
  });

  it("rejects unsupported export versions", () => {
    expect(() =>
      parseBenchmarkExport({
        format: "mneno.benchmark.result",
        version: 2,
      }),
    ).toThrow("Unsupported");
    expect(() =>
      parseTraceExport({
        format: "mneno.trace",
        version: 2,
        trace: {},
      }),
    ).toThrow("Unsupported");
  });

  it("parses a local failure report", () => {
    const report = parseFailureReport({
      id: "run-failures",
      benchmark: "locomo",
      run_id: "run-1",
      created_at: "2026-06-09T00:00:00Z",
      failures: [
        {
          id: "locomo:q1:mneno:retrieval_failure",
          benchmark: "locomo",
          case_id: "q1",
          provider: "mneno",
          category: "retrieval_failure",
          severity: "high",
          query: "Where?",
          expected_ids: ["D1:1"],
          retrieved_ids: [],
          included_ids: [],
          excluded_ids: [],
          forbidden_ids: [],
          trace_ids: ["trace-1"],
          reason: "Missing evidence.",
          evidence: ["missing_expected_ids=D1:1"],
          suggested_action: "Inspect retrieval.",
          metadata: {},
        },
      ],
      summary: {
        total_failures: 1,
        by_category: { retrieval_failure: 1 },
        by_provider: { mneno: 1 },
        by_severity: { high: 1 },
        top_suggested_actions: ["Inspect retrieval."],
      },
      metadata: {},
    });

    expect(report.summary.totalFailures).toBe(1);
    expect(report.mnenoOnly.totalFailures).toBe(1);
    expect(report.baselineOnly.totalFailures).toBe(0);
    expect(report.byProvider.mneno?.byCategory).toEqual({
      retrieval_failure: 1,
    });
    expect(report.failures[0]).toMatchObject({
      caseId: "q1",
      category: "retrieval_failure",
      traceIds: ["trace-1"],
      suggestedAction: "Mneno Core: Inspect retrieval.",
      expectedBehavior: false,
    });
  });

  it("infers provider interpretation for older baseline failure reports", () => {
    const report = parseFailureReport({
      id: "old-report",
      benchmark: "suite",
      run_id: "run-old",
      created_at: "2026-06-09T00:00:00Z",
      failures: [
        {
          id: "suite:q1:full_context_baseline:conflict_resolution_failure",
          benchmark: "suite",
          case_id: "q1",
          provider: "full_context_baseline",
          category: "conflict_resolution_failure",
          severity: "high",
          query: "What is current?",
          expected_ids: ["new"],
          retrieved_ids: ["new", "old"],
          included_ids: ["new", "old"],
          excluded_ids: [],
          forbidden_ids: ["old"],
          trace_ids: [],
          reason: "Forbidden memory was included.",
          evidence: ["used_forbidden_ids=old"],
          suggested_action: "Inspect conflict handling.",
          metadata: {},
        },
      ],
      summary: {
        total_failures: 1,
        by_category: { conflict_resolution_failure: 1 },
        by_provider: { full_context_baseline: 1 },
        by_severity: { high: 1 },
        top_suggested_actions: ["Inspect conflict handling."],
      },
      metadata: {},
    });

    expect(report.failures[0]).toMatchObject({
      expectedBehavior: true,
      interpretation: expect.stringContaining("intentionally includes all memories"),
      suggestedAction: expect.stringContaining("Comparison evidence:"),
    });
    expect(report.baselineOnly.totalFailures).toBe(1);
    expect(report.mnenoOnly.totalFailures).toBe(0);
  });

  it("parses Context Rot Suite category and skipped Mneno summaries", () => {
    const run = parseBenchmarkRun({
      run_id: "context-rot-1",
      suite: "mneno_context_rot_suite_v1",
      status: "completed",
      started_at: "2026-06-07T12:00:00Z",
      systems: ["keyword_baseline", "mneno"],
      results: [{ mneno_result: { status: "skipped" } }],
      export_metadata: {
        mneno_execution: {
          memories_loaded: 48,
          sessions_created: 12,
          conflicts_detected: 2,
          hierarchy_evaluated: true,
          hierarchy_transitions: { promoted: 1 },
          compaction_previewed: true,
          compaction_stats: { kept: 46 },
          traces_exported: 24,
          capability_errors: {},
          capability_report: {
            available: true,
            version: "0.4.0",
            capabilities: { build_context: true },
            missing: [],
            partial: false,
          },
        },
        context_rot_suite: {
          dataset: { memory_count: 48, case_count: 24 },
          systems: {
            keyword_baseline: {
              status: "completed",
              context_rot_score: 0.6,
              metrics: { expected_memory_recall: 0.5 },
              categories: {
                contradiction: {
                  case_count: 3,
                  context_rot_score: 0.7,
                  metrics: { expected_memory_recall: 0.66 },
                },
              },
            },
            mneno: {
              status: "skipped",
              context_rot_score: null,
              metrics: {},
              categories: {},
            },
          },
          report_path: "results/reports/context_rot_suite_latest.md",
          trace_directory: "results/mneno/traces",
          export_directory: "results/mneno/exports",
          failure_cases: [{ case_id: "case-1" }],
        },
      },
    });

    expect(run.mnenoStatus).toBe("skipped");
    expect(run.contextRot).toMatchObject({
      memoryCount: 48,
      caseCount: 24,
      failureCount: 1,
    });
    expect(run.contextRot?.systems[0]?.categories[0]).toMatchObject({
      category: "contradiction",
      caseCount: 3,
      contextRotScore: 0.7,
    });
    expect(run.mnenoExecution).toMatchObject({
      memoriesLoaded: 48,
      sessionsCreated: 12,
      conflictsDetected: 2,
      hierarchyEvaluated: true,
      compactionPreviewed: true,
      tracesExported: 24,
    });
  });

  it("parses LOCOMO dataset and system status", () => {
    const run = parseBenchmarkRun({
      run_id: "locomo-1",
      suite: "locomo",
      status: "dataset_missing",
      started_at: "2026-06-08T12:00:00Z",
      systems: ["keyword_baseline", "mneno"],
      results: [],
      export_metadata: {
        locomo: {
          dataset_status: "dataset_missing",
          execution_status: "skipped",
          dataset: {
            conversation_count: 0,
            message_count: 0,
            question_count: 0,
            categories: {},
          },
          systems: {
            mneno: {
              status: "skipped",
              metrics: {},
              trace_ids: [],
              skip_reason: "Dataset missing.",
              errors: [],
            },
          },
          official_scoring: {
            status: "not_implemented",
            reason: "Official scoring is pending.",
          },
          report_path: "results/locomo/locomo_latest.md",
          trace_directory: "results/locomo/traces",
          raw_output_directory: "results/locomo/raw",
        },
      },
    });

    expect(run.status).toBe("dataset_missing");
    expect(run.source).toBe("external");
    expect(run.locomo).toMatchObject({
      datasetStatus: "dataset_missing",
      executionStatus: "skipped",
      questionCount: 0,
    });
    expect(run.locomo?.systems[0]).toMatchObject({
      name: "mneno",
      status: "skipped",
    });
  });

  it("parses compact LOCOMO dashboard projections", () => {
    const run = parseBenchmarkRun({
      run_id: "locomo-dashboard",
      suite: "locomo",
      status: "completed",
      started_at: "2026-06-09T12:00:00Z",
      systems: ["keyword_baseline", "full_context_baseline", "mneno"],
      results: [],
      dashboard_case_count: 1986,
      dashboard_mneno_status: "completed",
      export_metadata: { locomo: { dataset: {}, systems: {} } },
    });

    expect(run.cases).toBe(1986);
    expect(run.mnenoStatus).toBe("completed");
  });

  it("parses retrieval deep-dive dashboard projections", () => {
    const report = parseRetrievalDeepDive({
      benchmark: "locomo",
      created_at: "2026-06-09T12:00:00Z",
      provider: "mneno",
      total_failures: 12,
      sampled_failures: [
        {
          id: "failure-1",
          case_id: "conv-1:qa-0001",
          provider: "mneno",
          conversation_id: "conv-1",
          question_type: "factual_recall",
          category: "factual_recall",
          question: "Where?",
          normalized_question: "where",
          expected_evidence: [{ evidence_id: "D1:1", text: "There." }],
          retrieved_candidates: [],
          context_package: { included_memories: [], excluded_memories: [] },
          trace: { trace_ids: ["trace-1"] },
          root_cause: "ranking_failure",
          explanation: "Evidence was not selected.",
        },
      ],
      root_causes: { ranking_failure: { count: 1, percentage: 100 } },
      statistics: {
        sample_size: 1,
        expected_evidence_count: 1,
        retrieved_expected_count: 0,
        candidate_expected_count: 1,
        retrieval_recall: 0,
        candidate_coverage: 1,
        failures_by_root_cause: {},
        failures_by_conversation: {},
        failures_by_question_type: {},
        failures_by_session: {},
        failures_by_category: {},
      },
    });

    expect(report.totalFailures).toBe(12);
    expect(report.rootCauses.ranking_failure?.percentage).toBe(100);
    expect(report.sampledFailures[0]).toMatchObject({
      caseId: "conv-1:qa-0001",
      rootCause: "ranking_failure",
      traceIds: ["trace-1"],
    });
  });
});
