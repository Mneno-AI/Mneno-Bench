import { describe, expect, it } from "vitest";

import {
  parseBenchmarkExport,
  parseBenchmarkRun,
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
});
